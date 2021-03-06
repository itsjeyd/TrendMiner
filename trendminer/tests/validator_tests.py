"""
Project: TrendMiner Demo Web Services
Authors: Christian Federmann <cfedermann@dfki.de>,
         Tim Krones <tkrones@coli.uni-saarland.de>
"""

import os
import shutil
import tempfile
import zipfile

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.test import TestCase
from django.test.client import Client

from settings import MAX_UPLOAD_SIZE, ROOT_PATH, TESTFILES_PATH
from trendminer import UploadFormErrors
from utils import add_timestamp_prefix, get_file_ext, remove_upload


class ValidatorTest(TestCase):
    """
    This class provides tests for form validators defined in
    `validators.py`.

    Each validator function is tested using a single method of this
    class. Test functions are named after the validator they test.
    They are prefixed with `test_`. The `setUpClass` method sets up
    the test environment and is called once *before* any of the
    individual tests are run. The `tearDownClass` method is
    responsible for cleaning up the test environment and is called
    once *after* all of the individual tests have run. The `setUp` and
    `tearDown` methods perform additional set up/clean up steps and
    are run before/after each individual test.
    """
    @classmethod
    def setUpClass(cls):
        """
        Set up test environment.

        This method creates a temporary folder for test files to be
        uploaded, defines a default prefix to be used for names of
        test files, and obtains the URL to upload files to via POST
        requests.

        The `uploaded_files` list initialized by this method is used
        to collect (names of) files that were uploaded by individual
        tests, making it possible to easily remove them later on.
        """
        cls.testdir = tempfile.mkdtemp(suffix='.test', dir=ROOT_PATH)
        cls.file_prefix = add_timestamp_prefix('')
        cls.analyse_url = reverse('analyse')
        cls.uploaded_files = []

    @classmethod
    def tearDownClass(cls):
        """
        Remove directory holding test files generated by individual
        tests, and call upon `__delete_uploaded_files to clear upload
        directory.
        """
        shutil.rmtree(cls.testdir)
        cls.__delete_uploaded_files()

    @classmethod
    def __delete_uploaded_files(cls):
        """
        Delete files uploaded by individual tests.
        """
        for upload in cls.uploaded_files:
            remove_upload(upload)

    def setUp(self):
        """
        Create `trendminer-demo` user in test DB and use it to log on
        to TrendMiner.

        In order to upload files to TrendMiner for analysis, users
        must be logged in. Since Django uses a separate database for
        testing purposes which is empty by default, a user needs to be
        created (and logged in) before running any tests targeting
        upload validation.
        """
        self.user = User.objects.create_user(
            username='trendminer-demo', password='trendminer-demo')
        self.browser = Client()
        self.browser.login(
            username=self.user.username, password='trendminer-demo')

    def tearDown(self):
        """
        Log out test user.
        """
        self.browser.logout()

    def __create_temp_file(self, extension, size):
        """
        Create a named temporary file with the specified extension and
        size in the (temporary) target directory for test files and
        return it.
        """
        temp_file = tempfile.NamedTemporaryFile(
            prefix=self.file_prefix, suffix=extension, dir=self.testdir)
        temp_file.truncate(size)
        return temp_file

    def __create_test_xml(self, name, content):
        """
        Create an XML file with the specified name and content in the
        (temporary) target directory for test files.
        """
        xml_file = open(
            os.path.join(self.testdir, name), 'w')
        xml_file.write(content)
        xml_file.close()
        return name

    def __create_test_zip(self, name, *files):
        """
        Create a .zip file in the (temporary) target directory for
        test files and add all files in `*files` to it.

        This method uses the string passed via the `name` parameter to
        name the .zip file. It expects all files to be added to the
        archive to be located in the target directory for test files.
        """
        zip_file = zipfile.ZipFile(
            os.path.join(self.testdir, name), 'w')
        os.chdir(self.testdir)
        for file_name in files:
            zip_file.write(os.path.basename(file_name))
        os.chdir(os.path.dirname(self.testdir))
        zip_file.close()
        return name

    def __open_test_file(self, file_path):
        """
        Open file located at `file_path` using the appropriate
        permissions and return it.
        """
        flag = 'rb' if not get_file_ext(file_path) == '.xml' else 'r'
        return open(file_path, flag)

    def __check_form_errors(self, file_name, expected_errors):
        """
        Upload file to TrendMiner and compare form errors to expected
        errors.

        `file_name` must be an absolute path to the test file.
        `expected_errors` should be a string (or a list of strings)
        representing the error message(s) TrendMiner is supposed to
        return for the test file.
        """
        with self.__open_test_file(file_name) as testfile:
            response = self.browser.post(self.analyse_url, {'data': testfile})
            self.assertFormError(
                response, form='form', field='data', errors=expected_errors)
        self.uploaded_files.append(os.path.basename(file_name))

    def test_ext_validator(self):
        """
        Check if extension validator correctly rejects files whose
        extension is not part of the list of accepted file types.

        To test the extension validator, this method creates a fake
        PNG file of size 1KB, uploads it to TrendMiner, and checks if
        the upload correctly fails with the appropriate message.
        """
        with self.__create_temp_file('.png', 1024) as temp_file:
            self.__check_form_errors(
                temp_file.name, UploadFormErrors.EXTENSION)

    def test_size_validator(self):
        """
        Check if size validator correctly rejects files whose size
        exceeds the maximum file size as specified by the
        `MAX_UPLOAD_SIZE` setting.

        To test the size validator, this method creates and uploads
        two fake files, both of which exceed the maximum file size for
        uploads by 1 byte. (The files are of type .zip and .xml,
        respectively, so they pass the extension validator.) It then
        checks if the uploads correctly fail with the appropriate
        message.
        """
        with self.__create_temp_file('.zip', MAX_UPLOAD_SIZE+1) as temp_file:
            self.__check_form_errors(temp_file.name, UploadFormErrors.SIZE)
        with self.__create_temp_file('.xml', MAX_UPLOAD_SIZE+1) as temp_file:
            self.__check_form_errors(temp_file.name, UploadFormErrors.SIZE)

    def test_mime_type_validator(self):
        """
        Check if MIME type validator correctly rejects files whose
        MIME types do not correspond to their extensions.

        To test the MIME type validator, this method creates and
        uploads a fake XML file and a fake .zip archive. Both files
        are of size 1KB. It then checks if the uploads correctly fail
        with the appropriate message.

        The error message defined for MIME type errors has two slots
        that need to be filled in: One for the file format as given by
        a file's extension, and one for the MIME type detected by the
        `file` command.
        """
        with self.__create_temp_file('.zip', 1024) as temp_file:
            self.__check_form_errors(
                temp_file.name, UploadFormErrors.MIME_TYPE.format(
                    '.zip', 'application/octet-stream'))
        with self.__create_temp_file('.xml', 1024) as temp_file:
            self.__check_form_errors(
                temp_file.name, UploadFormErrors.MIME_TYPE.format(
                    '.xml', 'application/octet-stream'))

    def test_zip_integrity_validator(self):
        """
        Check if .zip integrity validator correctly rejects archives
        that are corrupted.

        To test the .zip integrity validator, this method uploads a
        corrupted archive to TrendMiner and checks if the upload
        correctly fails with the appropriate message.
        """
        file_path = os.path.join(
            TESTFILES_PATH, '2013-01-01_12-00-00_corrupt.zip')
        if os.path.exists(file_path):
            self.__check_form_errors(
                file_path, UploadFormErrors.ZIP_INTEGRITY)

    def test_zip_contents_validator(self):
        """
        Check if .zip contents validator correctly rejects archives
        containing non-XML files.

        To test the .zip contents validator, this method first creates
        a fake PNG file. It then creates a real .zip archive and adds
        the PNG file to it. As a last step it uploads the archive to
        TrendMiner and checks if the upload correctly fails with the
        appropriate message.
        """
        with self.__create_temp_file('.png', 1024) as temp_file:
            test_zip = self.__create_test_zip(
                self.file_prefix+'png.zip', temp_file.name)
            self.__check_form_errors(
                os.path.join(self.testdir, test_zip),
                UploadFormErrors.ZIP_CONTENTS)

    def test_xml_wf_validator(self):
        """
        Check if XML well-formedness validator correctly rejects XML
        files and .zip archives containing XML files that are not
        well-formed.

        To test the XML well-formedness validator, this method creates
        an .xml file with malformed content and a .zip archive
        containing the .xml file. It uploads both of these files to
        TrendMiner and checks if the uploads correctly fail with the
        appropriate messages.
        """
        test_file = self.__create_test_xml(
            self.file_prefix+'malformed.xml', 'This is not valid XML.')
        self.__check_form_errors(
            os.path.join(self.testdir, test_file),
            UploadFormErrors.XML_WELLFORMEDNESS)
        test_zip = self.__create_test_zip(
            self.file_prefix+'malformed-xml.zip', test_file)
        self.__check_form_errors(
            os.path.join(self.testdir, test_zip),
            UploadFormErrors.FILES_WELLFORMEDNESS)

    def test_xml_schema_validator(self):
        """
        Check if XML schema validator correctly rejects XML files and
        .zip archives containing XML files that do not validate
        against the TrendMiner XML schema.

        To test the XML schema validator, this method creates an .xml
        file whose content is well-formed but does not conform to the
        TrendMiner XML schema, and a .zip archive containing the .xml
        file. It uploads both of these files to TrendMiner and checks
        if the uploads correctly fail with the appropriate messages.
        """
        test_file = self.__create_test_xml(
            self.file_prefix+'valid.xml',
            '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n' \
                '<document></document>')
        self.__check_form_errors(
            os.path.join(self.testdir, test_file),
            UploadFormErrors.XML_SCHEMA_CONFORMITY)
        test_zip = self.__create_test_zip(
            self.file_prefix+'valid-xml.zip', test_file)
        self.__check_form_errors(
            os.path.join(self.testdir, test_zip),
            UploadFormErrors.FILES_SCHEMA_CONFORMITY)

    def test_successful_cases(self):
        """
        Check if well-formed and schema-conforming XML files and .zip
        archives containing such files can be uploaded successfully to
        TrendMiner.

        This method creates an .xml file whose contents are well-formed
        and conform to the TrendMiner XML schema, and a .zip archive
        containing the .xml file. It uploads both of these files to
        TrendMiner and checks if they are accepted with a success
        message.
        """
        test_file = self.__create_test_xml(
            self.file_prefix+'schema-conforming.xml',
            '<item>\n' \
                '<identificativo>XY2013010101234</identificativo>\n' \
                '<data>2013-01-01</data>\n' \
                '<sigla>XY</sigla>\n' \
                '<classe>1</classe>\n' \
                '<dimensione>1234</dimensione>\n' \
                '<titolo></titolo>\n' \
                '<TESTATA></TESTATA>\n' \
                '<TITOLO></TITOLO>\n' \
                '<TESTO></TESTO>\n' \
                '<database>DOCTYPE=HTML</database>\n' \
                '</item>')
        with self.__open_test_file(
            os.path.join(self.testdir, test_file)) as testfile:
            response = self.browser.post(self.analyse_url, {'data': testfile})
            self.assertContains(response, 'Success!')
        self.uploaded_files.append(test_file)
        test_zip = self.__create_test_zip(
            self.file_prefix+'schema-conforming-xml.zip', test_file)
        with self.__open_test_file(
            os.path.join(self.testdir, test_zip)) as testfile:
            response = self.browser.post(self.analyse_url, {'data': testfile})
            self.assertContains(response, 'Success!')
        self.uploaded_files.append(test_zip)
