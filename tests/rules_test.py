# -*- coding: utf-8 -*-
"""Unit test for rules.py."""

import datetime
import inspect
import io

from absl.testing import absltest
from election_results_xml_validator import base
from election_results_xml_validator import rules
import github
from lxml import etree
from mock import MagicMock
from mock import mock_open
from mock import patch


class SchemaTest(absltest.TestCase):

  _schema_file = io.BytesIO(b"""<?xml version="1.0" encoding="UTF-8"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Report"/>
      <xs:complexType name="Person">
        <xs:sequence>
          <xs:element minOccurs="1" type="xs:string" name="FirstName" />
          <xs:element minOccurs="1" type="xs:string" name="LastName" />
          <xs:element minOccurs="0" type="xs:integer" name="Age" />
        </xs:sequence>
      </xs:complexType>
    </xs:schema>
  """)

  def testNoErrorForValidSchemaAndTree(self):
    root_string = """
      <Report>
        <Person>
          <FirstName>Jerry</FirstName>
          <LastName>Seinfeld</LastName>
          <Age>38</Age>
        </Person>
      </Report>
    """

    election_tree = etree.fromstring(root_string)
    schema_validator = rules.Schema(election_tree, SchemaTest._schema_file)
    schema_validator.check()

  def testRaisesErrorForSchemaParseFailure(self):
    schema_file = io.BytesIO(b"""<?xml version="1.0" encoding="UTF-8"?>
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="Report" type="CoolNewType"/>
      </xs:schema>
    """)

    election_tree = etree.fromstring("<Report/>")
    schema_validator = rules.Schema(election_tree, schema_file)

    with self.assertRaises(base.ElectionError) as ee:
      schema_validator.check()
    self.assertIn("schema file could not be parsed correctly",
                  str(ee.exception))

  def testRaisesErrorForInvalidTree(self):
    root_string = """
      <Person>
        <FirstName>Jerry</FirstName>
        <LastName>Seinfeld</LastName>
        <Age>38</Age>
      </Person>
    """

    election_tree = etree.fromstring(root_string)
    schema_validator = rules.Schema(election_tree, SchemaTest._schema_file)

    with self.assertRaises(base.ElectionTreeError) as ete:
      schema_validator.check()
    self.assertIn("election file didn't validate against schema",
                  str(ete.exception))


class OptionalAndEmptyTest(absltest.TestCase):

  def setUp(self):
    super(OptionalAndEmptyTest, self).setUp()
    self.optionality_validator = rules.OptionalAndEmpty(None, None)

  def testOnlyChecksOptionalElements(self):
    schema_file = io.BytesIO(b"""
      <element>
        <element minOccurs="0" name="ThingOne" />
        <element minOccurs="1" name="ThingTwo" />
        <element minOccurs="0" name="ThingThree" />
        <simpleType minOccurs="0" />
      </element>
    """)

    self.optionality_validator = rules.OptionalAndEmpty(None, schema_file)
    eligible_elements = self.optionality_validator.elements()

    self.assertLen(eligible_elements, 2)
    self.assertEqual(eligible_elements[0], "ThingOne")
    self.assertEqual(eligible_elements[1], "ThingThree")

  def testIgnoresIfElementIsSameAsPrevious(self):
    root_string = """
      <ThingOne></ThingOne>
    """

    non_empty_element = etree.fromstring(root_string)
    non_empty_element.sourceline = 7
    self.optionality_validator.previous = non_empty_element
    self.optionality_validator.check(non_empty_element)

  def testIgnoresNonEmptyElements(self):
    root_string = """
      <ThingOne>BoomShakalaka</ThingOne>
    """

    non_empty_element = etree.fromstring(root_string)
    non_empty_element.sourceline = 7
    self.optionality_validator.check(non_empty_element)

  def testThrowsWarningForEmptyElements_Null(self):
    empty_string = """
      <ThingOne></ThingOne>
    """

    empty_element = etree.fromstring(empty_string)
    empty_element.sourceline = 7
    with self.assertRaises(base.ElectionWarning):
      self.optionality_validator.check(empty_element)

  def testThrowsWarningForEmptyElements_Space(self):
    space_string = """
      <ThingOne>  </ThingOne>
    """

    space_element = etree.fromstring(space_string)
    space_element.sourceline = 7
    with self.assertRaises(base.ElectionWarning):
      self.optionality_validator.check(space_element)


class EncodingTest(absltest.TestCase):

  def testNoErrorForUTF8Encoding(self):
    root_string = io.BytesIO(b"""<?xml version="1.0" encoding="UTF-8"?>
      <Report/>
    """)

    election_tree = etree.parse(root_string)
    encoding_validator = rules.Encoding(election_tree, None)
    encoding_validator.check()

  def testRaisesErrorForNonUTF8Encoding(self):
    root_string = io.BytesIO(b"""<?xml version="1.0" encoding="us-ascii"?>
      <Report/>
    """)

    election_tree = etree.parse(root_string)
    encoding_validator = rules.Encoding(election_tree, None)

    with self.assertRaises(base.ElectionError) as ee:
      encoding_validator.check()
    self.assertEqual(str(ee.exception), "'Encoding on file is not UTF-8'")


class HungarianStyleNotationTest(absltest.TestCase):

  def setUp(self):
    super(HungarianStyleNotationTest, self).setUp()
    self.notation_validator = rules.HungarianStyleNotation(None, None)

  def testChecksAllElementsWithPrefixes(self):
    elements = self.notation_validator.elements()
    self.assertEqual(elements, self.notation_validator.elements_prefix.keys())

  def testIgnoresElementsWithNoObjectId(self):
    element_string = """
      <Party/>
    """

    party_element = etree.fromstring(element_string)
    self.notation_validator.check(party_element)

  def testObjectIdsUseAcceptedPrefix(self):
    elements_prefix = {
        "BallotMeasureContest": "bmc",
        "BallotMeasureSelection": "bms",
        "BallotStyle": "bs",
        "Candidate": "can",
        "CandidateContest": "cc",
        "CandidateSelection": "cs",
        "Coalition": "coa",
        "ContactInformation": "ci",
        "Hours": "hours",
        "Office": "off",
        "OfficeGroup": "og",
        "Party": "par",
        "PartyContest": "pc",
        "PartySelection": "ps",
        "Person": "per",
        "ReportingDevice": "rd",
        "ReportingUnit": "ru",
        "RetentionContest": "rc",
        "Schedule": "sched",
    }

    for elem in elements_prefix:
      element_string = """
        <{} objectId="{}0"/>
      """.format(elem, elements_prefix[elem])

      party_element = etree.fromstring(element_string)
      self.notation_validator.check(party_element)

  def testRaisesExceptionForInvalidPrefix(self):
    element_string = """
      <Party objectId="pax0"/>
    """

    party_element = etree.fromstring(element_string)
    with self.assertRaises(base.ElectionInfo):
      self.notation_validator.check(party_element)

  def testRaisesAnErrorForAnUnlistedElement(self):
    element_string = """
      <Blamo objectId="pax0"/>
    """

    party_element = etree.fromstring(element_string)
    with self.assertRaises(KeyError):
      self.notation_validator.check(party_element)


class LanguageCodeTest(absltest.TestCase):

  def setUp(self):
    super(LanguageCodeTest, self).setUp()
    self.language_code_validator = rules.LanguageCode(None, None)

  def testOnlyChecksTextElements(self):
    self.assertEqual(self.language_code_validator.elements(), ["Text"])

  def testIgnoresElementsWithoutLanguageAttribute(self):
    element_string = """
      <Text>BoomShakalaka</Text>
    """

    text_element = etree.fromstring(element_string)
    self.language_code_validator.check(text_element)

  def testLanguageAttributeIsValidTag(self):
    element_string = """
      <Text language="en">BoomShakalaka</Text>
    """

    text_element = etree.fromstring(element_string)
    self.language_code_validator.check(text_element)

  def testRaiseErrorForInvalidLanguageAttributes_Invalid(self):
    invalid_string = """
      <Text language="zzz">BoomShakalaka</Text>
    """

    invalid_element = etree.fromstring(invalid_string)
    with self.assertRaises(base.ElectionError):
      self.language_code_validator.check(invalid_element)

  def testRaiseErrorForInvalidLanguageAttributes_Empty(self):
    empty_string = """
      <Text language="">BoomShakalaka</Text>
    """

    empty_element = etree.fromstring(empty_string)
    with self.assertRaises(base.ElectionError):
      self.language_code_validator.check(empty_element)


class PercentSumTest(absltest.TestCase):

  def setUp(self):
    super(PercentSumTest, self).setUp()
    self.percent_validator = rules.PercentSum(None, None)
    self.root_string = """
      <Contest>
        <BallotSelection>
          <VoteCountsCollection>
            {}
          </VoteCountsCollection>
        </BallotSelection>
      </Contest>
    """

  def testOnlyChecksContestElements(self):
    self.assertEqual(["Contest"], self.percent_validator.elements())

  def testZeroPercentTotalIsValid(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>0.0</Count>
      </VoteCounts>
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>0.0</Count>
      </VoteCounts>
    """
    element_string = self.root_string.format(vote_counts)
    element = etree.fromstring(element_string)
    self.percent_validator.check(element)

  def testOneHundredPercentTotalIsValid(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>60.0</Count>
      </VoteCounts>
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>40.0</Count>
      </VoteCounts>
    """
    element_string = self.root_string.format(vote_counts)
    element = etree.fromstring(element_string)
    self.percent_validator.check(element)

  def testThrowsAnErrorForInvalidPercents(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>60.0</Count>
      </VoteCounts>
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>20.0</Count>
      </VoteCounts>
    """
    element_string = self.root_string.format(vote_counts)
    element = etree.fromstring(element_string)
    with self.assertRaises(base.ElectionError):
      self.percent_validator.check(element)

  def testOnlyUseCountForOtherTypeTotalPercent_RegularType(self):
    vote_counts = """
      <VoteCounts>
        <Type>total-percent</Type>
        <Count>60.0</Count>
      </VoteCounts>
      <VoteCounts>
        <Type>total-percent</Type>
        <Count>20.0</Count>
      </VoteCounts>
    """
    element_string = self.root_string.format(vote_counts)
    element = etree.fromstring(element_string)
    self.percent_validator.check(element)

  def testOnlyUseCountForOtherTypeTotalPercent_Invalid(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>percent-sum</OtherType>
        <Count>60.0</Count>
      </VoteCounts>
      <VoteCounts>
        <OtherType>percent-sum</OtherType>
        <Count>20.0</Count>
      </VoteCounts>
    """
    element_string = self.root_string.format(vote_counts)
    element = etree.fromstring(element_string)
    self.percent_validator.check(element)


class OnlyOneElectionTest(absltest.TestCase):

  def setUp(self):
    super(OnlyOneElectionTest, self).setUp()
    self.election_count_validator = rules.OnlyOneElection(None, None)

  def testOnlyChecksElectionReportElements(self):
    self.assertEqual(["ElectionReport"],
                     self.election_count_validator.elements())

  def testShouldHaveExactlyOneElection(self):
    root_string = """
    <ElectionReport>
      <Election></Election>
    </ElectionReport>
    """

    self.election_count_validator.check(etree.fromstring(root_string))

  def testThrowsErrorForMoreThanOneElection(self):
    root_string = """
    <ElectionReport>
      <Election></Election>
      <Election></Election>
    </ElectionReport>
    """

    with self.assertRaises(base.ElectionError):
      self.election_count_validator.check(etree.fromstring(root_string))


class EmptyTextTest(absltest.TestCase):

  def setUp(self):
    super(EmptyTextTest, self).setUp()
    self.empty_text_validator = rules.EmptyText(None, None)

  def testOnlyChecksTextElements(self):
    self.assertEqual(["Text"], self.empty_text_validator.elements())

  def testIgnoresNonEmptyElements(self):
    element_string = """
      <Text>Boomshakalaka</Text>
    """

    element = etree.fromstring(element_string)
    self.empty_text_validator.check(element)

  def testIgnoresEmptyElements(self):
    element_string = """
      <Text></Text>
    """

    element = etree.fromstring(element_string)
    self.empty_text_validator.check(element)

  def testThrowsWarningForSpaceOnlyElements(self):
    empty_string = """
      <Text>   </Text>
    """

    element = etree.fromstring(empty_string)
    with self.assertRaises(base.ElectionWarning):
      self.empty_text_validator.check(element)


class DuplicateIDTest(absltest.TestCase):

  def testValidIfNoObjectIDValuesAreTheSame(self):
    root_string = """
      <Report objectId="1">
        <Person>
          <FirstName objectId="">Jerry</FirstName>
          <LastName objectId="">Seinfeld</LastName>
          <Age objectId="5">38</Age>
        </Person>
      </Report>
    """

    election_tree = etree.fromstring(root_string)
    duplicate_id_validator = rules.DuplicateID(election_tree, None)
    duplicate_id_validator.check()

  def testThrowErrorIfObjectIDsAreTheSame(self):
    root_string = """
      <Report objectId="1">
        <Person objectId="2">
          <FirstName objectId="3">Jerry</FirstName>
          <LastName objectId="4">Seinfeld</LastName>
          <Age objectId="4">38</Age>
        </Person>
      </Report>
    """

    election_tree = etree.fromstring(root_string)
    duplicate_id_validator = rules.DuplicateID(election_tree, None)
    with self.assertRaises(base.ElectionTreeError):
      duplicate_id_validator.check()


class ValidIDREFTest(absltest.TestCase):

  _schema_file = io.BytesIO(b"""<?xml version="1.0" encoding="UTF-8"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Report"/>
      <xs:complexType name="Office">
        <xs:sequence>
            <xs:element minOccurs="0" name="ElectoralDistrictId" type="xs:IDREF" />
            <xs:element minOccurs="0" name="FilingDeadline" type="xs:date" />
            <xs:element minOccurs="0" name="IsPartisan" type="xs:boolean" />
            <xs:element minOccurs="0" name="OfficeHolderPersonIds" type="xs:IDREFS" />
        </xs:sequence>
      </xs:complexType>
    </xs:schema>
  """)

  def testGathersAllObjectIDsOnCreation(self):
    root_string = """
      <Report objectId="1">
        <Person>
          <FirstName objectId="">Jerry</FirstName>
          <LastName objectId="">Seinfeld</LastName>
          <Age objectId="5">38</Age>
        </Person>
      </Report>
    """

    element = etree.fromstring(root_string)
    id_ref_validator = rules.ValidIDREF(element, None)
    expected_ids = set(["1", "5"])

    self.assertEqual(id_ref_validator.all_object_ids, expected_ids)

  def testChecksAllElementsWithIDREFType(self):
    root_string = """
      <Report/>
    """

    element = etree.fromstring(root_string)
    id_ref_validator = rules.ValidIDREF(element, ValidIDREFTest._schema_file)
    expected_elements = ["ElectoralDistrictId", "OfficeHolderPersonIds"]

    self.assertEqual(id_ref_validator.elements(), expected_elements)

  def testValidIfElementTextReferencesObjectIDOrEmpty(self):
    root_string = """
      <Report objectId="1">
        <GpUnit objectId="ab-123" />
        <GpUnit objectId="cd-456" />
        <Office>
          <ElectoralDistrictId>ab-123 cd-456</ElectoralDistrictId>
          <ElectoralDistrictId></ElectoralDistrictId>
          <FilingDeadline>2019-01-01</FilingDeadline>
          <IsPartisan>true</IsPartisan>
          <OfficeHolderPersonIds>cd-456</OfficeHolderPersonIds>
        </Office>
      </Report>
    """

    root_element = etree.fromstring(root_string)
    id_ref_validator = rules.ValidIDREF(root_element,
                                        ValidIDREFTest._schema_file)

    ref_elem_one = root_element.find("Office").findall("ElectoralDistrictId")[0]
    ref_elem_two = root_element.find("Office").findall("ElectoralDistrictId")[1]
    ref_elem_three = root_element.find("Office").find("OfficeHolderPersonIds")

    id_ref_validator.check(ref_elem_one)
    id_ref_validator.check(ref_elem_two)
    id_ref_validator.check(ref_elem_three)

  def testThrowsErrorIfElementTextFailsToReferencesObjectID(self):
    root_string = """
      <Report objectId="1">
        <GpUnit objectId="ab-123" />
        <GpUnit objectId="cd-456" />
        <Office>
          <ElectoralDistrictId>ab-123 xy-987</ElectoralDistrictId>
          <FilingDeadline>2019-01-01</FilingDeadline>
          <IsPartisan>true</IsPartisan>
          <OfficeHolderPersonIds>cd-456</OfficeHolderPersonIds>
        </Office>
      </Report>
    """

    root_element = etree.fromstring(root_string)
    id_ref_validator = rules.ValidIDREF(root_element,
                                        ValidIDREFTest._schema_file)

    ref_element_one = root_element.find("Office").find("ElectoralDistrictId")
    ref_element_two = root_element.find("Office").find("OfficeHolderPersonIds")

    with self.assertRaises(base.ElectionError):
      id_ref_validator.check(ref_element_one)
    id_ref_validator.check(ref_element_two)


class ElectoralDistrictOcdIdTest(absltest.TestCase):

  def setUp(self):
    super(ElectoralDistrictOcdIdTest, self).setUp()
    root_string = """
      <ElectionReport>
        <GpUnitCollection>
          <GpUnit/>
          <GpUnit/>
          <GpUnit/>
        </GpUnitCollection>
      </ElectionReport>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)

    open_mod = inspect.getmodule(open)
    if "__builtins__" not in open_mod.__dict__.keys():
      # '__builtin__' for python2
      self.builtins_name = open_mod.__name__
    else:
      # 'builtins' for python3
      self.builtins_name = open_mod.__builtins__["__name__"]

    # mock open function call to read provided csv data
    downloaded_ocdid_file = "id,name\nocd-division/country:ar,Argentina"
    self.mock_open_func = mock_open(read_data=downloaded_ocdid_file)

  def testSetsDefaultValuesUponCreation(self):
    self.assertTrue(self.ocdid_validator.check_github)
    self.assertIsNone(self.ocdid_validator.country_code)
    self.assertIsNone(self.ocdid_validator.github_file)
    self.assertIsNone(self.ocdid_validator.github_repo)
    self.assertIsNone(self.ocdid_validator.local_file)
    self.assertLen(self.ocdid_validator.gpunits, 3)

  # setup tests
  def testSetOCDsToResultOfGetOcdData(self):
    mock_ocdids = ["ocdid1", "ocdid2"]
    mock = MagicMock(return_value=mock_ocdids)
    self.ocdid_validator._get_ocd_data = mock
    self.ocdid_validator.local_file = "://file/path"
    self.ocdid_validator.setup()

    self.assertEqual(None, self.ocdid_validator.github_file)
    self.assertEqual(1, mock.call_count)
    self.assertEqual(mock_ocdids, self.ocdid_validator.ocds)

  def testSetsGithubFileIfNoLocalFile(self):
    self.ocdid_validator.country_code = "us"
    mock_ocdids = ["ocdid1", "ocdid2"]
    mock = MagicMock(return_value=mock_ocdids)
    self.ocdid_validator._get_ocd_data = mock
    self.ocdid_validator.setup()

    self.assertEqual("country-us.csv", self.ocdid_validator.github_file)
    self.assertEqual(1, mock.call_count)
    self.assertEqual(mock_ocdids, self.ocdid_validator.ocds)

  # _get_latest_commit_date tests
  def testReturnsTheLatestCommitDateForTheCountryCSV(self):
    self.ocdid_validator.github_file = "country-ar.csv"
    self.ocdid_validator.github_repo = github.Repository.Repository(
        None, [], [], None)

    now = datetime.datetime.now()
    formatted_commit_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = github.Commit.Commit(
        None, {},
        dict({
            "commit": dict({"committer": dict({"date": formatted_commit_date})})
        }), None)

    mock_get_commits = MagicMock(return_value=[commit])
    self.ocdid_validator.github_repo.get_commits = mock_get_commits

    latest_commit_date = self.ocdid_validator._get_latest_commit_date()
    self.assertEqual(now.replace(microsecond=0), latest_commit_date)
    mock_get_commits.assert_called_with(path="identifiers/country-ar.csv")

  # _download_data tests
  def testItCopiesDownloadedDataToCacheFileWhenValid(self):
    self.ocdid_validator.github_file = "country-ar.csv"
    self.ocdid_validator._verify_data = MagicMock(return_value=True)
    mock_request = MagicMock()
    mock_io_open = MagicMock()
    mock_copy = MagicMock()

    # pylint: disable=g-backslash-continuation
    with patch("requests.get", mock_request), \
         patch("io.open", mock_io_open), \
         patch("shutil.copy", mock_copy):
      self.ocdid_validator._download_data("/usr/cache")

    request_url = "https://raw.github.com/{0}/master/{1}/country-ar.csv".format(
        self.ocdid_validator.GITHUB_REPO, self.ocdid_validator.GITHUB_DIR)
    mock_request.assert_called_with(request_url)
    mock_io_open.assert_called_with("/usr/cache.tmp", "wb")
    mock_copy.assert_called_with("/usr/cache.tmp", "/usr/cache")

  def testItRaisesAnErrorAndDoesNotCopyDataWhenTheDataIsInvalid(self):
    self.ocdid_validator.github_file = "country-ar.csv"
    self.ocdid_validator._verify_data = MagicMock(return_value=False)
    mock_copy = MagicMock()

    # pylint: disable=g-backslash-continuation
    with patch("requests.get", MagicMock()), \
         patch("io.open", MagicMock()), \
         patch("shutil.copy", mock_copy), \
         self.assertRaises(base.ElectionError):
      self.ocdid_validator._download_data("/usr/cache")

    self.assertEqual(0, mock_copy.call_count)

  # _get_latest_file_blob_sha tests
  def testItReturnsTheBlobShaOfTheGithubFileWhenFound(self):
    content_file = github.ContentFile.ContentFile(
        None, {}, dict({
            "name": "country-ar.csv",
            "sha": "abc123"
        }), None)
    repo = github.Repository.Repository(None, {}, {}, None)
    repo.get_dir_contents = MagicMock(return_value=[content_file])
    self.ocdid_validator.github_repo = repo
    self.ocdid_validator.github_file = "country-ar.csv"

    blob_sha = self.ocdid_validator._get_latest_file_blob_sha()
    self.assertEqual("abc123", blob_sha)

  def testItReturnsNoneIfTheFileCantBeFound(self):
    content_file = github.ContentFile.ContentFile(
        None, {}, dict({
            "name": "country-ar.csv",
            "sha": "abc123"
        }), None)
    repo = github.Repository.Repository(None, {}, {}, None)
    repo.get_dir_contents = MagicMock(return_value=[content_file])
    self.ocdid_validator.github_repo = repo
    self.ocdid_validator.github_file = "country-us.csv"

    blob_sha = self.ocdid_validator._get_latest_file_blob_sha()
    self.assertIsNone(blob_sha)

  # _encode_ocdid_value tests
  def testItReturnsTheProvidedValueIfTypeString(self):
    ocdid = str("my-cool-ocdid")
    result = self.ocdid_validator._encode_ocdid_value(ocdid)
    self.assertEqual("my-cool-ocdid", result)

  def testItReturnsEncodedValueIfTypeUnicode(self):
    ocdid = u"regionalwahlkreis:burgenland_süd"
    result = self.ocdid_validator._encode_ocdid_value(ocdid)

    encoded = "regionalwahlkreis:burgenland_süd"
    self.assertEqual(encoded, result)

  def testItReturnsEmptyStringIfOtherType(self):
    ocdid = 1
    result = self.ocdid_validator._encode_ocdid_value(ocdid)
    self.assertEqual("", result)

  # elements test
  def testItOnlyChecksElectoralDistrictIdElements(self):
    self.assertEqual(["ElectoralDistrictId"], self.ocdid_validator.elements())

  # check tests
  def testThatGivenElectoralDistrictIdReferencesGpUnitWithValidOCDID(self):
    parent_string = """
      <Contest objectId="con123">
        <ElectoralDistrictId>ru0002</ElectoralDistrictId>
      </Contest>
    """
    element = etree.fromstring(parent_string)

    gp_unit = """
      <GpUnit objectId="ru0002">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us/state:va</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    self.ocdid_validator.gpunits = [etree.fromstring(gp_unit)]
    self.ocdid_validator.ocds = set(["ocd-division/country:us/state:va"])

    self.ocdid_validator.check(element.find("ElectoralDistrictId"))

  def testIgnoresElementsWhoDontHaveContestParent(self):
    parent_string = """
      <Party><ElectoralDistrictId/></Party>
    """
    element = etree.fromstring(parent_string)

    self.ocdid_validator.check(element.find("ElectoralDistrictId"))

  def testIgnoresElementsWhoseParentHasNoObjectId(self):
    parent_string = """
      <Contest><ElectoralDistrictId/></Contest>
    """
    element = etree.fromstring(parent_string)

    self.ocdid_validator.check(element.find("ElectoralDistrictId"))

  def testItRaisesAnErrorIfTheOcdidLabelIsNotAllLowerCase(self):
    parent_string = """
      <Contest objectId="con123">
        <ElectoralDistrictId>ru0002</ElectoralDistrictId>
      </Contest>
    """
    element = etree.fromstring(parent_string)

    gp_unit = """
      <GpUnit objectId="ru0002">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>oCd-id</Type>
            <Value>ocd-division/country:us/state:va</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    self.ocdid_validator.gpunits = [etree.fromstring(gp_unit)]
    self.ocdid_validator.ocds = set(["ocd-division/country:us/state:va"])

    with self.assertRaises(base.ElectionError) as ee:
      self.ocdid_validator.check(element.find("ElectoralDistrictId"))
    self.assertIn("Should be ocd-id and not oCd-id", str(ee.exception))

  def testItRaisesAnErrorIfTheReferencedGpUnitDoesNotExist(self):
    parent_string = """
      <Contest objectId="con123">
        <ElectoralDistrictId>ru9999</ElectoralDistrictId>
      </Contest>
    """
    element = etree.fromstring(parent_string)

    gp_unit = """
      <GpUnit objectId="ru0002">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us/state:va</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    self.ocdid_validator.gpunits = [etree.fromstring(gp_unit)]
    self.ocdid_validator.ocds = set(["ocd-division/country:us/state:va"])

    with self.assertRaises(base.ElectionError) as ee:
      self.ocdid_validator.check(element.find("ElectoralDistrictId"))
    self.assertIn("con123 does not refer to a GpUnit", str(ee.exception))

  def testItRaisesAnErrorIfTheReferencedGpUnitHasNoExternalId(self):
    parent_string = """
      <Contest objectId="con123">
        <ElectoralDistrictId>ru0002</ElectoralDistrictId>
      </Contest>
    """
    element = etree.fromstring(parent_string)

    gp_unit = """
      <GpUnit objectId="ru0002">
        <ExternalIdentifiers>
        </ExternalIdentifiers>
      </GpUnit>
    """
    self.ocdid_validator.gpunits = [etree.fromstring(gp_unit)]
    self.ocdid_validator.ocds = set(["ocd-division/country:us/state:va"])

    with self.assertRaises(base.ElectionError) as ee:
      self.ocdid_validator.check(element.find("ElectoralDistrictId"))
    self.assertIn("does not have any external identifiers", str(ee.exception))

  def testItRaisesAnErrorIfTheReferencedOcdidIsNotValid(self):
    parent_string = """
      <Contest objectId="con123">
        <ElectoralDistrictId>ru0002</ElectoralDistrictId>
      </Contest>
    """
    element = etree.fromstring(parent_string)

    gp_unit = """
      <GpUnit objectId="ru0002">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>ocd-id</Type>
            <Value>ocd-division/country:us/state:ma</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </GpUnit>
    """
    self.ocdid_validator.gpunits = [etree.fromstring(gp_unit)]
    self.ocdid_validator.ocds = set(["ocd-division/country:us/state:va"])

    with self.assertRaises(base.ElectionError) as ee:
      self.ocdid_validator.check(element.find("ElectoralDistrictId"))
    self.assertIn("does not have a valid OCD", str(ee.exception))

  def testUnicodeOCDIDsAreValid(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland_süd"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set([ocd_value])
    self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))

  def testCountryOCDIDsAreValid(self):
    ocd_value = "ocd-division/country:la"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set([ocd_value])
    self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))

  def testLongOCDIDsAreValid(self):
    ocd_value = "ocd-division/country:us/state:la"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set([ocd_value])
    self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))

  def testUnicodeOCDIDsAreValid_fails(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:kärnten_west"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)

    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set(
        ["ocd-division/country:la"
         "/regionalwahlkreis:burgenland_süd"])
    with self.assertRaises(base.ElectionError) as cm:
      self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))
    self.assertIn("does not have a valid OCD", str(cm.exception))

  def testInvalidUnicodeOCDIDs_fails(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland_süd/"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set([ocd_value])
    with self.assertRaises(base.ElectionError) as cm:
      self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))
    self.assertIn("does not have a valid OCD", str(cm.exception))

  def testInvalidNonUnicodeOCDIDs_fails(self):
    ocd_value = "regionalwahlkreis:burgenland_sued"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set(["regionalwahlkreis:karnten_west"])
    with self.assertRaises(base.ElectionError) as cm:
      self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))
    self.assertIn("does not have a valid OCD", str(cm.exception))

  def testInvalidNonUnicodeOCDIDsWithAnInvalidCharacter_fails(self):
    ocd_value = "ocd-division/country:la/regionalwahlkreis:burgenland*d"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set([ocd_value])
    with self.assertRaises(base.ElectionError) as cm:
      self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))
    self.assertIn("does not have a valid OCD", str(cm.exception))

  def testNonUnicodeOCDIDsAreValid(self):
    ocd_value = "ocd-division/country:to/regionalwahlkreis:burgenland_sued"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set([ocd_value])
    self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))

  def testNonUnicodeOCDIDsAreValid_fails(self):
    ocd_value = "ocd-division/country:to/regionalwahlkreis:burgenland_sued"
    root_string = """
      <Contest objectId="ru_at_999">
        <ElectoralDistrictId>cc_at_999</ElectoralDistrictId>
        <GpUnit objectId="cc_at_999" type="ReportingUnit">
           <ExternalIdentifiers>
             <ExternalIdentifier>
               <Type>ocd-id</Type>
               <Value>""" + ocd_value + """</Value>
             </ExternalIdentifier>
           </ExternalIdentifiers>
        </GpUnit>
      </Contest>
    """
    election_tree = etree.fromstring(root_string)
    self.ocdid_validator = rules.ElectoralDistrictOcdId(election_tree, None)
    self.ocdid_validator.ocds = set(
        ["ocd-division/country:to"
         "/regionalwahlkreis:karnten_west"])
    with self.assertRaises(base.ElectionError) as cm:
      self.ocdid_validator.check(election_tree.find("ElectoralDistrictId"))
    self.assertIn("does not have a valid OCD", str(cm.exception))


class GpUnitOcdIdTest(absltest.TestCase):

  def setUp(self):
    super(GpUnitOcdIdTest, self).setUp()
    root_string = """
      <ElectionReport>
        <GpUnitCollection>
          <GpUnit/>
          <GpUnit/>
          <GpUnit/>
        </GpUnitCollection>
      </ElectionReport>
    """
    election_tree = etree.fromstring(root_string)
    self.gp_unit_validator = rules.GpUnitOcdId(election_tree, None)

    open_mod = inspect.getmodule(open)
    if "__builtins__" not in open_mod.__dict__.keys():
      # '__builtin__' for python2
      self.builtins_name = open_mod.__name__
    else:
      # 'builtins' for python3
      self.builtins_name = open_mod.__builtins__["__name__"]

    # mock open function call to read provided csv data
    downloaded_ocdid_file = "id,name\nocd-division/country:ar,Argentina"
    self.mock_open_func = mock_open(read_data=downloaded_ocdid_file)

    self.base_reporting_unit = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <GpUnit objectId="ru0030" xsi:type="ReportingUnit">
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>ocd-id</Type>
              {}
            </ExternalIdentifier>
          </ExternalIdentifiers>
          <Name>Middlesex County</Name>
          <Number>3</Number>
          <Type>{}</Type>
        </GpUnit>
      </ElectionReport>
    """

  def testItOnlyChecksReportingUnitElements(self):
    self.assertEqual(["ReportingUnit"], self.gp_unit_validator.elements())

  def testItChecksTheGivenReportingUnitHasAValidOcdid(self):
    reporting_unit = self.base_reporting_unit.format(
        "<Value>ocd-division/country:us/state:ma/county:middlesex</Value>",
        "county")
    report = etree.fromstring(reporting_unit)

    self.gp_unit_validator.ocds = set(
        ["ocd-division/country:us/state:ma/county:middlesex"])
    self.gp_unit_validator.check(report.find("GpUnit"))

  def testItIgnoresElementsWithNoObjectId(self):
    reporting_unit = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <GpUnit xsi:type="ReportingUnit"/>
      </ElectionReport>
    """
    report = etree.fromstring(reporting_unit)

    self.gp_unit_validator.check(report.find("GpUnit"))

  def testItIgnoresElementsWithoutProperDistrictType(self):
    reporting_unit = self.base_reporting_unit.format(
        "<Value>ocd-division/country:us/state:ma/county:middlesex</Value>",
        "county-council",
    )
    report = etree.fromstring(reporting_unit)

    self.gp_unit_validator.ocds = set(["ocd-division/country:us"])
    self.gp_unit_validator.check(report.find("GpUnit"))

  def testItIgnoresElementsWithNoOcdIdValue(self):
    reporting_unit = self.base_reporting_unit.format("", "county")
    report = etree.fromstring(reporting_unit)

    self.gp_unit_validator.ocds = set(
        ["ocd-division/country:us/state:ma/county:middlesex"])
    self.gp_unit_validator.check(report.find("GpUnit"))

  def testItRaisesAWarningIfOcdIdNotInListOfValidIds(self):
    reporting_unit = self.base_reporting_unit.format(
        "<Value>ocd-division/country:us/state:ny/county:nassau</Value>",
        "county",
    )
    report = etree.fromstring(reporting_unit)

    self.gp_unit_validator.ocds = set(
        ["ocd-division/country:us/state:ma/county:middlesex"])
    with self.assertRaises(base.ElectionWarning):
      self.gp_unit_validator.check(report.find("GpUnit"))


class DuplicateGpUnitsTest(absltest.TestCase):

  def setUp(self):
    super(DuplicateGpUnitsTest, self).setUp()
    self.gp_unit_validator = rules.DuplicateGpUnits(None, None)
    self.root_string = """
    <GpUnitCollection>
    {}
    </GpUnitCollection>
    """

  def testNoGpUnitsReturnsNone(self):
    self.gp_unit_validator.check(etree.fromstring(self.root_string))

  def testNoObjectIdsReturnsNone(self):
    test_string = """
      <GpUnit>
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit>
        <ComposingGpUnitIds>xyz987</ComposingGpUnitIds>
        <Name>New York</Name>
        <Type>state</Type>
      </GpUnit>
    """
    self.gp_unit_validator.check(
        etree.fromstring(self.root_string.format(test_string)))

  def testNoComposingGpUnitsReturnsNone(self):
    test_string = """
      <GpUnit>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit>
        <Name>New York</Name>
        <Type>state</Type>
      </GpUnit>
    """
    self.gp_unit_validator.check(
        etree.fromstring(self.root_string.format(test_string)))

  def testNoComposingGpUnitsTextReturnsNone(self):
    test_string = """
      <GpUnit>
        <ComposingGpUnitIds></ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit>
        <Name>New York</Name>
        <Type>state</Type>
      </GpUnit>
    """
    self.gp_unit_validator.check(
        etree.fromstring(self.root_string.format(test_string)))

  def testItProcessesCollectionAndDoesNotFindDuplicates(self):
    test_string = """
      <GpUnit objectId="ru0002">
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="ru0003">
        <ComposingGpUnitIds></ComposingGpUnitIds>
        <Name>Massachusetts</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit>
        <ComposingGpUnitIds>xyz987</ComposingGpUnitIds>
        <Name>New York</Name>
        <Type>state</Type>
      </GpUnit>
    """
    self.gp_unit_validator.check(
        etree.fromstring(self.root_string.format(test_string)))

  def testItProcessesCollectionAndFindsDuplicatePaths(self):
    test_string = """
      <GpUnit objectId="ru0002">
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="abc123">
        <ComposingGpUnitIds></ComposingGpUnitIds>
        <Name>Massachusetts</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="ru0004">
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
    """
    with self.assertRaises(base.ElectionError) as cm:
      self.gp_unit_validator.check(
          etree.fromstring(self.root_string.format(test_string)))
    self.assertIn("GpUnits ('ru0002', 'ru0004') are duplicates",
                  str(cm.exception))

  def testItProcessesCollectionAndFindsDuplicateObjectIds(self):
    test_string = """
      <GpUnit objectId="ru0002">
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="abc123">
        <ComposingGpUnitIds></ComposingGpUnitIds>
        <Name>Massachusetts</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="ru0002">
        <ComposingGpUnitIds>abc124</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
    """
    with self.assertRaises(base.ElectionError) as cm:
      self.gp_unit_validator.check(
          etree.fromstring(self.root_string.format(test_string)))
    self.assertIn("GpUnit with object_id ru0002 is duplicated",
                  str(cm.exception))

  def testItFindsDuplicateObjectIdsAndDuplicatePaths(self):
    test_string = """
      <GpUnit objectId="ru0002">
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="ru0002">
        <ComposingGpUnitIds></ComposingGpUnitIds>
        <Name>Massachusetts</Name>
        <Type>state</Type>
      </GpUnit>
      <GpUnit objectId="ru0004">
        <ComposingGpUnitIds>abc123</ComposingGpUnitIds>
        <Name>Virginia</Name>
        <Type>state</Type>
      </GpUnit>
    """
    with self.assertRaises(base.ElectionError) as cm:
      self.gp_unit_validator.check(
          etree.fromstring(self.root_string.format(test_string)))
    self.assertIn("GpUnit with object_id ru0002 is duplicated",
                  str(cm.exception))
    self.assertIn("GpUnits ('ru0002', 'ru0004') are duplicates",
                  str(cm.exception))


class OtherTypeTest(absltest.TestCase):

  def setUp(self):
    super(OtherTypeTest, self).setUp()
    self.other_type_validator = rules.OtherType(None, None)

  def testOnlyChecksComplexTypesThatContainOtherTypeElement(self):
    schema_file = io.BytesIO(b"""<?xml version="1.0" encoding="UTF-8"?>
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="Report"/>
        <xs:complexType name="Device">
          <xs:sequence>
              <xs:element minOccurs="0" name="Manufacturer" type="xs:string" />
              <xs:element minOccurs="0" name="Model" type="xs:string" />
              <xs:element minOccurs="0" name="Type" type="DeviceType" />
              <xs:element minOccurs="0" name="OtherType" type="xs:string" />
          </xs:sequence>
        </xs:complexType>
      </xs:schema>
    """)

    validator = rules.OtherType(None, schema_file)

    expected_elements = ["Device"]
    eligible_elements = validator.elements()

    self.assertEqual(expected_elements, eligible_elements)

  def testItChecksForExistenceOfOtherType(self):
    complex_element_string = """
      <Device>
        <Manufacturer>Google</Manufacturer>
        <Model>Pixel</Model>
        <Type>other</Type>
        <OtherType>Best phone ever</OtherType>
      </Device>
    """

    complex_element = etree.fromstring(complex_element_string)
    self.other_type_validator.check(complex_element)

  def testItIgnoresElementsWithNoType(self):
    complex_element_string = """
      <Device>
        <Manufacturer>Google</Manufacturer>
        <Model>Pixel</Model>
      </Device>
    """

    complex_element = etree.fromstring(complex_element_string)
    self.other_type_validator.check(complex_element)

  def testItRaisesErrorIfOtherTypeNotPresent(self):
    complex_element_string = """
      <Device>
        <Manufacturer>Google</Manufacturer>
        <Model>Pixel</Model>
        <Type>other</Type>
      </Device>
    """

    complex_element = etree.fromstring(complex_element_string)
    with self.assertRaises(base.ElectionError):
      self.other_type_validator.check(complex_element)


class PartisanPrimaryTest(absltest.TestCase):

  _base_report = """
    <ElectionReport>
      <Election>
        {}
      </Election>
    </ElectionReport>
  """

  def testSetsElectionTypeOnCreation_Primary(self):
    election_details = "<Type>primary</Type>"
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertEqual("primary", prim_part_validator.election_type)

  def testSetsElectionTypeOnCreation_None(self):
    election_string = """
      <ElectionReport/>
    """
    election_tree = etree.fromstring(election_string)
    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertIsNone(prim_part_validator.election_type)

  def testSetsElectionTypeOnCreation_NoType(self):
    election_details = """
      <Name>
        <Text language="en">2020 New York City Mayor</Text>
      </Name>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertIsNone(prim_part_validator.election_type)

  # elements tests
  def testOnlyChecksCandidateContestsForSpecificElections_Primary(self):
    election_details = "<Type>primary</Type>"
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertEqual(["CandidateContest"], prim_part_validator.elements())

  def testOnlyChecksCandidateContestsForSpecificElections_Open(self):
    election_details = "<Type>partisan-primary-open</Type>"
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertEqual(["CandidateContest"], prim_part_validator.elements())

  def testOnlyChecksCandidateContestsForSpecificElections_Closed(self):
    election_details = "<Type>partisan-primary-closed</Type>"
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertEqual(["CandidateContest"], prim_part_validator.elements())

  def testOnlyChecksCandidateContestsForSpecificElections_General(self):
    election_details = "<Type>general</Type>"
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimary(election_tree, None)
    self.assertEqual([], prim_part_validator.elements())

  # check tests
  def testPartyIdsArePresentAndNonEmpty(self):
    election_details = """
      <CandidateContest>
        <PrimaryPartyIds>abc123</PrimaryPartyIds>
      </CandidateContest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)

    contest = root.find("Election").find("CandidateContest")
    rules.PartisanPrimary(root, None).check(contest)

  def testRaisesErrorIfPartyIdsDoNotExist_NoParty(self):
    election_details = """
      <Type>primary</Type>
      <CandidateContest>
        <Name>2020 Election</Name>
      </CandidateContest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)

    election = root.find("Election")
    election.sourceline = 7
    contest = election.find("CandidateContest")

    with self.assertRaises(base.ElectionWarning):
      rules.PartisanPrimary(root, None).check(contest)

  def testRaisesErrorIfPartyIdsDoNotExist_EmptyParty(self):
    election_details = """
      <Type>primary</Type>
      <CandidateContest>
        <PrimaryPartyIds></PrimaryPartyIds>
        <Name>2020 Election</Name>
      </CandidateContest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)

    election = root.find("Election")
    election.sourceline = 7
    contest = election.find("CandidateContest")

    with self.assertRaises(base.ElectionWarning):
      rules.PartisanPrimary(root, None).check(contest)

  def testRaisesErrorIfPartyIdsDoNotExist_WhiteSpace(self):
    election_details = """
      <Type>primary</Type>
      <CandidateContest>
        <PrimaryPartyIds>      </PrimaryPartyIds>
        <Name>2020 Election</Name>
      </CandidateContest>
    """
    election_string = PartisanPrimaryTest._base_report.format(election_details)
    root = etree.fromstring(election_string)

    election = root.find("Election")
    election.sourceline = 7
    contest = election.find("CandidateContest")

    with self.assertRaises(base.ElectionWarning):
      rules.PartisanPrimary(root, None).check(contest)


class PartisanPrimaryHeuristicTest(absltest.TestCase):

  _base_election_report = """
    <ElectionReport>
      <Election>
        {}
      </Election>
    </ElectionReport>
  """

  _general_candidate_contest = """
    <Type>general</Type>
    <CandidateContest>
      {}
    </CandidateContest>
  """

  _base_candidate_contest = _base_election_report.format(
      _general_candidate_contest)

  def testChecksNonPrimaryCandidateContests_NoType(self):
    election_details = "<Name>2020 election</Name>"
    election_string = self._base_election_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimaryHeuristic(election_tree, None)
    self.assertEqual(["CandidateContest"], prim_part_validator.elements())

  def testChecksNonPrimaryCandidateContests_General(self):
    election_details = "<Type>general</Type>"
    election_string = self._base_election_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimaryHeuristic(election_tree, None)
    self.assertEqual(["CandidateContest"], prim_part_validator.elements())

  def testChecksNonPrimaryCandidateContests_Primary(self):
    election_details = "<Type>primary</Type>"
    election_string = self._base_election_report.format(election_details)
    election_tree = etree.fromstring(election_string)

    prim_part_validator = rules.PartisanPrimaryHeuristic(election_tree, None)
    self.assertEqual([], prim_part_validator.elements())

  def testIgnoresContestsThatDoNotSuggestPrimary_NoName(self):
    contest_details = "<PrimaryPartyIds>abc123</PrimaryPartyIds>"
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    no_name_contest = root.find("Election").find("CandidateContest")
    rules.PartisanPrimaryHeuristic(root, None).check(no_name_contest)

  def testIgnoresContestsThatDoNotSuggestPrimary_EmptyName(self):
    contest_details = """
      <Name></Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    empty_name_contest = root.find("Election").find("CandidateContest")
    rules.PartisanPrimaryHeuristic(root, None).check(empty_name_contest)

  def testIgnoresContestsThatDoNotSuggestPrimary_NotPrimary(self):
    contest_details = """
      <Name>for sure not a primary</Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    contest = root.find("Election").find("CandidateContest")
    rules.PartisanPrimaryHeuristic(root, None).check(contest)

  def testThrowsWarningIfPossiblePrimaryDetected_Dem(self):
    contest_details = """
      <Name>Might Be Primary (dem)</Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    dem_contest = root.find("Election").find("CandidateContest")
    dem_contest.sourceline = 7
    with self.assertRaises(base.ElectionWarning):
      rules.PartisanPrimaryHeuristic(root, None).check(dem_contest)

  def testThrowsWarningIfPossiblePrimaryDetected_Rep(self):
    contest_details = """
      <Name>Might Be Primary (rep)</Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    rep_contest = root.find("Election").find("CandidateContest")
    rep_contest.sourceline = 7
    with self.assertRaises(base.ElectionWarning):
      rules.PartisanPrimaryHeuristic(root, None).check(rep_contest)

  def testThrowsWarningIfPossiblePrimaryDetected_Lib(self):
    contest_details = """
      <Name>Might Be Primary (lib)</Name>
      <PrimaryPartyIds>abc123</PrimaryPartyIds>
    """
    root_string = self._base_candidate_contest.format(contest_details)
    root = etree.fromstring(root_string)

    lib_contest = root.find("Election").find("CandidateContest")
    lib_contest.sourceline = 7
    with self.assertRaises(base.ElectionWarning):
      rules.PartisanPrimaryHeuristic(root, None).check(lib_contest)


class CoalitionPartiesTest(absltest.TestCase):

  _base_election_coalition = """
    <Election>
      <Coalition>
        {}
      </Coalition>
    </Election>
  """

  def testEachCoalitionHasDefinedPartyId(self):
    root_string = """
      <Election>
        <Coalition>
          <PartyIds>abc123</PartyIds>
        </Coalition>
        <Coalition>
          <PartyIds>def456</PartyIds>
        </Coalition>
      </Election>
    """
    election_tree = etree.fromstring(root_string)
    rules.CoalitionParties(election_tree, None).check()

  def testRaisesErrorIfCoalitionDoesNotDefinePartyId_NoPartyId(self):
    no_party_string = self._base_election_coalition.format("")
    election_tree = etree.fromstring(no_party_string)

    with self.assertRaises(base.ElectionError):
      rules.CoalitionParties(election_tree, None).check()

  def testRaisesErrorIfCoalitionDoesNotDefinePartyId_EmptyPartyId(self):
    coalition_details = "<PartyIds></PartyIds>"
    empty_party_string = self._base_election_coalition.format(coalition_details)
    election_tree = etree.fromstring(empty_party_string)

    with self.assertRaises(base.ElectionError):
      rules.CoalitionParties(election_tree, None).check()

  def testRaisesErrorIfCoalitionDoesNotDefinePartyId_Whitespace(self):
    coalition_details = "<PartyIds>     </PartyIds>"
    all_space_party_string = self._base_election_coalition.format(
        coalition_details)
    election_tree = etree.fromstring(all_space_party_string)

    with self.assertRaises(base.ElectionError):
      rules.CoalitionParties(election_tree, None).check()


class UniqueLabelTest(absltest.TestCase):

  def testChecksElementsWithTypeInternationalizedText(self):
    schema_file = io.BytesIO(b"""<?xml version="1.0" encoding="UTF-8"?>
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="Report" type="CoolNewType">
          <xs:complexType name="ContactInformation">
            <xs:sequence>
                <xs:element maxOccurs="unbounded" minOccurs="0" name="AddressLine" type="xs:string" />
                <xs:element maxOccurs="1" minOccurs="0" name="Directions" type="InternationalizedText" />
            </xs:sequence>
          </xs:complexType>
          <xs:complexType name="PollingInformation">
            <xs:sequence>
                <xs:element maxOccurs="unbounded" minOccurs="0" name="AddressLine" type="xs:string" />
                <xs:element maxOccurs="1" minOccurs="0" name="Directions" type="InternationalizedText" />
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:schema>
    """)

    label_validator = rules.UniqueLabel(None, schema_file)
    self.assertEqual(["Directions"], label_validator.elements())

  def testMakesSureAllLabelsAreUnique(self):
    unique_element_label_string = """
      <Directions label="us-standard"/>
    """
    element = etree.fromstring(unique_element_label_string)
    label_validator = rules.UniqueLabel(None, None)
    label_validator.check(element)

    no_element_label_string = """
      <Directions/>
    """
    element = etree.fromstring(no_element_label_string)
    label_validator = rules.UniqueLabel(None, None)
    label_validator.check(element)

  def testRaisesErrorIfNotAllLabelsAreUnique(self):
    unique_element_label_string = """
      <Directions label="us-standard"/>
    """
    element = etree.fromstring(unique_element_label_string)
    label_validator = rules.UniqueLabel(None, None)
    label_validator.labels = set(["us-standard"])
    with self.assertRaises(base.ElectionError):
      label_validator.check(element)


class CandidatesReferencedOnceTest(absltest.TestCase):

  _election_report = """
    <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <ContestCollection>
        {}
      </ContestCollection>
      {}
    </ElectionReport>
  """

  _candidate_collection = """
    <CandidateCollection>
      <Candidate objectId="can99999a"/>
      <Candidate objectId="can99999b" />
      <Candidate objectId="can11111a" />
      <Candidate objectId="can11111b" />
      <Candidate objectId="can45678a" />
      {}
    </CandidateCollection>
  """

  _base_candidate_contest = """
    <Contest objectId="con1234">
      <BallotSelection objectId="cs12345" xsi:type="CandidateSelection">
        <CandidateIds>can99999a can99999b</CandidateIds>
      </BallotSelection>
      <BallotSelection objectId="cs98765" xsi:type="CandidateSelection">
        <CandidateIds>can11111a can11111b</CandidateIds>
      </BallotSelection>
      <BallotSelection xsi:type="CandidateSelection">
        <CandidateIds>can45678a</CandidateIds>
      </BallotSelection>
    </Contest>
  """

  _base_retention_contest = """
    <Contest objectId="con5678">
      <CandidateId>can99999a</CandidateId>
      <BallotSelection objectId="cs12345" xsi:type="BallotMeasureSelection">
        <Selection>
          <Text language="en">Yes</Text>
        </Selection>
      </BallotSelection>
      <BallotSelection objectId="cs98765" xsi:type="BallotMeasureSelection">
        <Selection>
          <Text language="en">No</Text>
        </Selection>
      </BallotSelection>
    </Contest>
  """

  # _register_candidates test
  def testMapsCandIdsToTheContestsThatReferenceThem_CandContest(self):
    candidate_string = self._candidate_collection.format(
        "<Candidate objectId='can54321'/>")
    root_string = self._election_report.format(
        self._base_candidate_contest, candidate_string)
    election_tree = etree.fromstring(root_string)
    cand_validator = rules.CandidatesReferencedOnce(election_tree, None)

    expected_seen_candidates = dict({
        "can99999a": ["con1234"],
        "can99999b": ["con1234"],
        "can11111a": ["con1234"],
        "can11111b": ["con1234"],
        "can45678a": ["con1234"],
        "can54321": [],
    })
    cand_validator._register_candidates()
    self.assertEqual(
        expected_seen_candidates, cand_validator.candidate_registry)

  def testMapsCandIdsToTheContestsThatReferenceThem_RetentionContest(self):
    candidate_string = self._candidate_collection.format(
        "<Candidate objectId='can54321'/>")
    root_string = self._election_report.format(
        self._base_retention_contest, candidate_string)
    election_tree = etree.fromstring(root_string)
    cand_validator = rules.CandidatesReferencedOnce(election_tree, None)

    expected_seen_candidates = dict({
        "can99999a": ["con5678"],
        "can99999b": [],
        "can11111a": [],
        "can11111b": [],
        "can45678a": [],
        "can54321": [],
    })
    cand_validator._register_candidates()
    self.assertEqual(
        expected_seen_candidates, cand_validator.candidate_registry)

  def testMapsCandIdsToTheContestsThatReferenceThem_MultiContest(self):
    candidate_string = self._candidate_collection.format(
        "<Candidate objectId='can54321'/>")
    two_contests = self._base_candidate_contest + self._base_retention_contest
    root_string = self._election_report.format(two_contests, candidate_string)
    election_tree = etree.fromstring(root_string)
    cand_validator = rules.CandidatesReferencedOnce(election_tree, None)

    expected_seen_candidates = dict({
        "can99999a": ["con1234", "con5678"],
        "can99999b": ["con1234"],
        "can11111a": ["con1234"],
        "can11111b": ["con1234"],
        "can45678a": ["con1234"],
        "can54321": [],
    })
    cand_validator._register_candidates()
    self.assertEqual(
        expected_seen_candidates, cand_validator.candidate_registry)

  # check tests
  def testItChecksThatEachCandidateOnlyMapsToOneContest(self):
    root_string = self._election_report.format(
        self._base_candidate_contest, self._candidate_collection)
    election_tree = etree.fromstring(root_string)
    candidate_validator = rules.CandidatesReferencedOnce(election_tree, None)

    candidate_validator.check()

  def testRaisesAnErrorIfACandidateMapsToMultipleContests(self):
    two_contests = self._base_candidate_contest + self._base_retention_contest
    root_string = self._election_report.format(
        two_contests, self._candidate_collection)
    election_tree = etree.fromstring(root_string)
    candidate_validator = rules.CandidatesReferencedOnce(election_tree, None)

    with self.assertRaises(base.ElectionTreeError) as ete:
      candidate_validator.check()
    self.assertIn(
        "The Election File contains invalid Candidate references",
        str(ete.exception))
    self.assertIn("can99999a", ete.exception.error_log[0].message)
    self.assertIn("con1234", ete.exception.error_log[0].message)
    self.assertIn("con5678", ete.exception.error_log[0].message)

  def testRaisesAnErrorIfACandidateIsNotReferencedInAContest(self):
    candidate_string = self._candidate_collection.format(
        "<Candidate objectId='can54321'/>")
    root_string = self._election_report.format(
        self._base_candidate_contest, candidate_string)
    election_tree = etree.fromstring(root_string)
    candidate_validator = rules.CandidatesReferencedOnce(election_tree, None)

    with self.assertRaises(base.ElectionTreeError) as ete:
      candidate_validator.check()
    self.assertIn(
        "The Election File contains invalid Candidate references",
        str(ete.exception))
    self.assertIn("can54321 is not referenced",
                  ete.exception.error_log[0].message)


class ProperBallotSelectionTest(absltest.TestCase):

  def setUp(self):
    super(ProperBallotSelectionTest, self).setUp()
    self.ballot_selection_validator = rules.ProperBallotSelection(None, None)

  def testItShouldCheckAllElementsListedAsKeysInSelectionMapping(self):
    elements = self.ballot_selection_validator.elements()

    self.assertLen(elements, 4)
    self.assertIn("BallotMeasureContest", elements)
    self.assertIn("CandidateContest", elements)
    self.assertIn("PartyContest", elements)
    self.assertIn("RetentionContest", elements)

  def testAllSelectionsInContestAreOfMatchingType(self):
    contest_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Contest objectId="cc20002" xsi:type="CandidateContest">
          <BallotSelection objectId="cs111" xsi:type="CandidateSelection"/>
          <BallotSelection objectId="cs222" xsi:type="CandidateSelection"/>
          <BallotSelection objectId="cs333" xsi:type="CandidateSelection"/>
        </Contest>
      </ElectionReport>
    """
    element = etree.fromstring(contest_string)
    self.ballot_selection_validator.check(element.find("Contest"))

  def testRaisesAnErrorIfAllSelectionsInContestAreNotOfMatchingType(self):
    contest_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Contest objectId="cc20002" xsi:type="CandidateContest">
          <BallotSelection objectId="cs111" xsi:type="CandidateSelection"/>
          <BallotSelection objectId="cs222" xsi:type="PartySelection"/>
          <BallotSelection objectId="cs333" xsi:type="CandidateSelection"/>
        </Contest>
      </ElectionReport>
    """
    element = etree.fromstring(contest_string)
    with self.assertRaises(base.ElectionError):
      self.ballot_selection_validator.check(element.find("Contest"))


class PartiesHaveValidColorsTest(absltest.TestCase):

  def setUp(self):
    super(PartiesHaveValidColorsTest, self).setUp()
    self._base_string = """
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
          </Name>
          {}
        </Party>
    """
    self._color_str = "<Color>{}</Color>"
    self.color_validator = rules.PartiesHaveValidColors(None, None)

  def testPartiesHaveValidColorsLowercase(self):
    root_string = self._base_string.format(self._color_str.format("ff0000"))
    element = etree.fromstring(root_string)
    self.color_validator.check(element)

  def testPartiesHaveValidColorsUppercase(self):
    root_string = self._base_string.format(self._color_str.format("FF0000"))
    element = etree.fromstring(root_string)
    self.color_validator.check(element)

  def testColorHasPoundSign(self):
    root_string = self._base_string.format(self._color_str.format("#0000ff"))
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionWarning) as cm:
      self.color_validator.check(element)
    self.assertIn("is not a valid hex color", str(cm.exception))
    self.assertIn("par0001", str(cm.exception))

  def testColorTagMissingValue(self):
    root_string = self._base_string.format(self._color_str.format(""))
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionWarning) as cm:
      self.color_validator.check(element)
    self.assertIn("is missing a value", str(cm.exception))
    self.assertIn("par0001", str(cm.exception))

  def testPartiesHaveNonHex(self):
    root_string = self._base_string.format(self._color_str.format("green"))
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionWarning) as cm:
      self.color_validator.check(element)
    self.assertIn("is not a valid hex color", str(cm.exception))
    self.assertIn("par0001", str(cm.exception))

  def testPartyHasMoreThanOneColor(self):
    root_string = """
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
          </Name>
          <Color>ff0000</Color>
          <Color>008800</Color>
        </Party>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionWarning) as cm:
      self.color_validator.check(element)
    self.assertIn("has more than one color", str(cm.exception))
    self.assertIn("par0001", str(cm.exception))


class ValidateDuplicateColorsTest(absltest.TestCase):

  def setUp(self):
    super(ValidateDuplicateColorsTest, self).setUp()
    self._base_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
          </Name>
          {0}
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
          </Name>
          {1}
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Green</Text>
          </Name>
          {2}
        </Party>
      </PartyCollection>
    """
    self._color_str = "<Color>{}</Color>"
    self.color_validator = rules.ValidateDuplicateColors(None, None)

  def testPartiesHaveDuplicateColors(self):
    root_string = self._base_string.format(
        self._color_str.format("ff0000"),
        self._color_str.format("ff0000"),
        self._color_str.format("ff0000"),
    )
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.color_validator.check(element)
    self.assertIn("parties with duplicate colors", str(cm.exception))

  def testPartiesHaveUniqueColors(self):
    root_string = self._base_string.format(
        self._color_str.format("ff0000"), self._color_str.format("0000ff"),
        self._color_str.format("008000"))
    element = etree.fromstring(root_string)
    self.color_validator.check(element)


class DuplicatedPartyAbbreviationTest(absltest.TestCase):

  def setUp(self):
    super(DuplicatedPartyAbbreviationTest, self).setUp()
    self.parties_validator = rules.DuplicatedPartyAbbreviation(
        None, None)

  def testPartyCollectionWithoutParty(self):
    root_string = """
      <PartyCollection>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed contains duplicated party abbreviations",
                  str(cm.exception))

  def testPartyWithoutInternationalizedAbbreviation(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
        </Party>
        <Party objectId="par0002">
          <InternationalizedAbbreviation>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratic</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed contains duplicated party abbreviations",
                  str(cm.exception))

  def testDuplicateInternationalizedAbbreviation(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Republican</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0002">
          <InternationalizedAbbreviation>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratic</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed contains duplicated party abbreviations",
                  str(cm.exception))

  def testNoDuplicatedInternationalizedAbbreviation(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0002">
          <InternationalizedAbbreviation>
            <Text language="en">Democratic</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Green</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    self.parties_validator.check(element)


class PersonHasUniqueFullNameTest(absltest.TestCase):

  def setUp(self):
    super(PersonHasUniqueFullNameTest, self).setUp()
    self.people_validator = rules.PersonHasUniqueFullName(None, None)

  def testEmptyPersonCollection(self):
    root_string = """
      <PersonCollection>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("The feed contains people with duplicated name",
                  str(cm.exception))

  def testPersonCollectionWithDuplicatedFullNameWithoutBirthday(self):
    root_string = """
      <PersonCollection>
        <Person objectId="per_gb_6459172">
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
        </Person>
        <Person objectId="per_gb_6436252">
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
        </Person>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("The feed contains people with duplicated name",
                  str(cm.exception))

  def testPersonCollectionWithDuplicatedFullNameWithBirthday(self):
    root_string = """
      <PersonCollection>
        <Person objectId="per_gb_6456562">
          <FirstName>Jamie</FirstName>
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
          <DateOfBirth>1944-12-11</DateOfBirth>
        </Person>
        <Person objectId="per_gb_64201052">
          <FirstName>Jamie</FirstName>
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
          <DateOfBirth>1944-12-11</DateOfBirth>
        </Person>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("The feed contains people with duplicated name",
                  str(cm.exception))

  def testPersonCollectionWithDuplicatedFullNameButDifferentBirthday(self):
    root_string = """
      <PersonCollection>
        <Person objectId="per_gb_600452">
          <FirstName>Jamie</FirstName>
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
          <DateOfBirth>1944-12-11</DateOfBirth>
        </Person>
        <Person objectId="per_gb_6456322">
          <FirstName>Jamie</FirstName>
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
          <DateOfBirth>1972-11-20</DateOfBirth>
        </Person>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)
    self.people_validator.check(element)

  def testPersonCollectionWithoutFullNameButSameName(self):
    root_string = """
      <PersonCollection>
        <Person objectId="per_gb_647452">
          <FirstName>Jamie</FirstName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
        </Person>
        <Person objectId="per_gb_640052">
          <FirstName>Jamie</FirstName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
        </Person>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("The feed contains people with duplicated name",
                  str(cm.exception))

  def testPersonCollectionWithoutInformation(self):
    root_string = """
      <PersonCollection>
        <Person objectId="per_gb_6455552">
          <Gender>M</Gender>
        </Person>
        <Person objectId="per_gb_6456322">
          <Gender>M</Gender>
        </Person>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.people_validator.check(element)
    self.assertIn("The feed contains people with duplicated name",
                  str(cm.exception))

  def testPersonCollectionWithoutAnyWarning(self):
    root_string = """
      <PersonCollection>
        <Person objectId="per_gb_64532">
          <FirstName>Jamie</FirstName>
          <FullName>
            <Text language="en">Jamie David Adams</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Adams</LastName>
          <MiddleName>David</MiddleName>
          <DateOfBirth>1992-12-20</DateOfBirth>
        </Person>
        <Person objectId="per_gb_647752">
          <FirstName>Arthur</FirstName>
          <FullName>
            <Text language="en">Arthur Maupassant Maurice</Text>
          </FullName>
          <Gender>M</Gender>
          <LastName>Maurice</LastName>
          <MiddleName>Maupassant</MiddleName>
          <DateOfBirth>1972-11-20</DateOfBirth>
        </Person>
      </PersonCollection>
    """
    element = etree.fromstring(root_string)
    self.people_validator.check(element)


class DuplicatedPartyNameTest(absltest.TestCase):

  def setUp(self):
    super(DuplicatedPartyNameTest, self).setUp()
    self.parties_validator = rules.DuplicatedPartyName(None, None)

  def testPartyCollectionWithoutParty(self):
    root_string = """
      <PartyCollection>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed contains duplicated party names", str(cm.exception))

  def testPartyWithoutName(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratic</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed contains duplicated party names", str(cm.exception))

  def testDuplicatePartyName(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratic</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed contains duplicated party names", str(cm.exception))

  def testUniquePartyName(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Green</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    self.parties_validator.check(element)


class MissingPartyNameTranslationTest(absltest.TestCase):

  def setUp(self):
    super(MissingPartyNameTranslationTest, self).setUp()
    self.parties_validator = rules.MissingPartyNameTranslation(
        None, None)

  def testPartyCollectionWithoutParty(self):
    root_string = """
      <PartyCollection>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed is missing several parties name translation",
                  str(cm.exception))

  def testPartyWithoutName(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratic</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed is missing several parties name translation",
                  str(cm.exception))

  def testMissingTranslationAtTheBeginning(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratico</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed is missing several parties name translation",
                  str(cm.exception))

  def testMissingTranslationInTheMiddle(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0002">
          <Name>
            <Text language="en">Democratic</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn("The feed is missing several parties name translation",
                  str(cm.exception))

  def testWithAllGoodTranslation(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Republican</Text>
          </Name>
        </Party>
        <Party objectId="par0003">
          <Name>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </Name>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    self.parties_validator.check(element)


class MissingPartyAbbreviationTranslationTest(absltest.TestCase):

  def setUp(self):
    super(MissingPartyAbbreviationTranslationTest, self).setUp()
    self.parties_validator = rules.MissingPartyAbbreviationTranslation(
        None, None)

  def testPartyCollectionWithoutParty(self):
    root_string = """
      <PartyCollection>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn(
        "The feed is missing several parties abbreviation translation",
        str(cm.exception))

  def testPartyWithoutInternationalizedAbbreviation(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
        </Party>
        <Party objectId="par0002">
          <InternationalizedAbbreviation>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratic</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn(
        "The feed is missing several parties abbreviation translation",
        str(cm.exception))

  def testMissingTranslationAtTheBeginning(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0002">
          <InternationalizedAbbreviation>
            <Text language="en">Democratic</Text>
            <Text language="ro">Democratico</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn(
        "The feed is missing several parties abbreviation translation",
        str(cm.exception))

  def testMissingTranslationInTheMiddle(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Republican</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0002">
          <InternationalizedAbbreviation>
            <Text language="en">Democratic</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionTreeInfo) as cm:
      self.parties_validator.check(element)
    self.assertIn(
        "The feed is missing several parties abbreviation translation",
        str(cm.exception))

  def testWithAllGoodTranslation(self):
    root_string = """
      <PartyCollection>
        <Party objectId="par0001">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Republican</Text>
          </InternationalizedAbbreviation>
        </Party>
        <Party objectId="par0003">
          <InternationalizedAbbreviation>
            <Text language="en">Republican</Text>
            <Text language="ro">Others</Text>
          </InternationalizedAbbreviation>
        </Party>
      </PartyCollection>
    """
    element = etree.fromstring(root_string)
    self.parties_validator.check(element)


class MissingPartyAffiliationTest(absltest.TestCase):

  _base_xml_string = """
    <xml>
      {}
      {}
      {}
    </xml>
  """

  _candidate_collection = """
    <CandidateCollection>
      <Candidate>
        <PartyId>par0002</PartyId>
      </Candidate>
      <Candidate/>
    </CandidateCollection>
  """

  _person_collection = """
    <PersonCollection>
      <Person objectId="p1">
        <PartyId>par0001</PartyId>
      </Person>
      <Person objectId="p1">
        <PartyId></PartyId>
      </Person>
      <Person objectId="p2" />
      <Person objectId="p3" />
    </PersonCollection>
  """

  _party_collection = """
    <PartyCollection>
      <Party objectId="par0001">
        <Name>
          <Text language="en">Republican</Text>
        </Name>
      </Party>
      <Party objectId="par0002">
        <Name>
          <Text language="en">Democratic</Text>
        </Name>
      </Party>
      <Party objectId="par0003">
        <Name>
          <Text language="en">Libertarian</Text>
        </Name>
      </Party>
    </PartyCollection>
  """

  # _gather_reference_values tests
  def testReturnsPartyIdsFromCandidatesAndPeople(self):
    root_string = self._base_xml_string.format(self._candidate_collection,
                                               self._person_collection,
                                               self._party_collection)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    party_validator = rules.MissingPartyAffiliation(election_tree, None)

    reference_values = party_validator._gather_reference_values()
    expected_reference_values = set(["par0002", "par0001"])
    self.assertEqual(expected_reference_values, reference_values)

  def testReturnsCandidatePartyIdsIfNoPersonCollection(self):
    root_string = self._base_xml_string.format(self._party_collection, "",
                                               self._candidate_collection)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    party_validator = rules.MissingPartyAffiliation(election_tree, None)

    reference_values = party_validator._gather_reference_values()
    expected_reference_values = set(["par0002"])
    self.assertEqual(expected_reference_values, reference_values)

  def testReturnsPersonPartyIdsIfNoCandidateCollection(self):
    root_string = self._base_xml_string.format(self._party_collection,
                                               self._person_collection, "")
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    party_validator = rules.MissingPartyAffiliation(election_tree, None)

    reference_values = party_validator._gather_reference_values()
    expected_reference_values = set(["par0001"])
    self.assertEqual(expected_reference_values, reference_values)

  def testIgnoresPartyIdElementsWithInvalidText(self):
    candidate_collection = """
      <CandidateCollection>
        <Candidate>
          <PartyId>   </PartyId>
        </Candidate>
        <Candidate/>
      </CandidateCollection>
    """
    root_string = self._base_xml_string.format(self._party_collection,
                                               self._person_collection,
                                               candidate_collection)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    party_validator = rules.MissingPartyAffiliation(election_tree, None)

    reference_values = party_validator._gather_reference_values()
    expected_reference_values = set(["par0001"])
    self.assertEqual(expected_reference_values, reference_values)

  # _gather_defined_values tests
  def testReturnsObjectIdsFromPartyCollectionParties(self):
    root_string = self._base_xml_string.format(self._candidate_collection,
                                               self._person_collection,
                                               self._party_collection)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    party_validator = rules.MissingPartyAffiliation(election_tree, None)

    defined_values = party_validator._gather_defined_values()
    expected_defined_values = set(["par0002", "par0001", "par0003"])
    self.assertEqual(expected_defined_values, defined_values)

  def testReturnsAnEmptySetIfNoCollection(self):
    root_string = self._base_xml_string.format(self._candidate_collection,
                                               self._person_collection, "")
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    party_validator = rules.MissingPartyAffiliation(election_tree, None)

    defined_values = party_validator._gather_defined_values()
    self.assertEqual(set(), defined_values)

  # check tests
  def testCheckEachPartyIdReferenceHasAPartyElement(self):
    root_string = self._base_xml_string.format(self._party_collection,
                                               self._person_collection,
                                               self._candidate_collection)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    party_validator = rules.MissingPartyAffiliation(election_tree, None)
    party_validator.check()

  def testIgnoresTreesWithNoRoot(self):
    no_root_string = io.BytesIO(b"<OfficeCollection/>")
    election_tree = etree.parse(no_root_string)
    party_validator = rules.MissingPartyAffiliation(election_tree, None)
    party_validator.check()

  def testRaisesErrorIfThereIsNoPartyCollection(self):
    root_string = self._base_xml_string.format("", self._person_collection,
                                               self._candidate_collection)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    party_validator = rules.MissingPartyAffiliation(election_tree, None)

    with self.assertRaises(base.ElectionError):
      party_validator.check()

  def testRaisesErrorIfPartyIdDoesNotReferencePartyElement(self):
    root_string = io.BytesIO(b"""
      <xml>
        <PartyCollection>
          <Party objectId="par0001">
            <Name>
              <Text language="en">Republican</Text>
            </Name>
          </Party>
          <Party objectId="par0002">
            <Name>
              <Text language="en">Democratic</Text>
            </Name>
          </Party>
        </PartyCollection>
        <PersonCollection>
          <Person objectId="p1">
            <PartyId>par0001</PartyId>
          </Person>
          <Person objectId="p2" />
          <Person objectId="p3" />
        </PersonCollection>
        <CandidateCollection>
          <Candidate>
            <PartyId>par0003</PartyId>
          </Candidate>
        </CandidateCollection>
      </xml>
    """)
    election_tree = etree.parse(root_string)
    party_validator = rules.MissingPartyAffiliation(election_tree, None)
    with self.assertRaises(base.ElectionError) as ee:
      party_validator.check()
    self.assertIn("No defined Party for par0003 found in the feed.",
                  str(ee.exception))


class DuplicateContestNamesTest(absltest.TestCase):

  _base_report = """
    <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <ContestCollection>
        <Contest objectId="cc11111" xsi:type="CandidateContest">
          {}
        </Contest>
        <Contest objectId="cc22222" xsi:type="CandidateContest">
          {}
        </Contest>
        <Contest objectId="cc33333" xsi:type="CandidateContest">
          {}
        </Contest>
      </ContestCollection>
    </ElectionReport>
  """

  def testEveryContestHasAUniqueName(self):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    tres = "<Name>Treasurer</Name>"
    root_string = self._base_report.format(pres, sec, tres)
    election_tree = etree.fromstring(root_string)
    duplicate_validator = rules.DuplicateContestNames(election_tree, None)
    duplicate_validator.check()

  def testRaisesAnErrorIfContestIsMissingNameOrNameIsEmpty_Missing(self):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    root_string = self._base_report.format(pres, sec, "")
    election_tree = etree.fromstring(root_string)
    duplicate_validator = rules.DuplicateContestNames(election_tree, None)
    with self.assertRaises(base.ElectionTreeError):
      duplicate_validator.check()

  def testRaisesAnErrorIfContestIsMissingNameOrNameIsEmpty_Empty(self):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    empty = "<Name></Name>"
    root_string = self._base_report.format(pres, sec, empty)
    election_tree = etree.fromstring(root_string)
    duplicate_validator = rules.DuplicateContestNames(election_tree, None)
    with self.assertRaises(base.ElectionTreeError):
      duplicate_validator.check()

  def testRaisesAnErrorIfNameIsNotUnique(self):
    pres = "<Name>President</Name>"
    sec = "<Name>Secretary</Name>"
    duplicate = "<Name>President</Name>"
    root_string = self._base_report.format(pres, sec, duplicate)
    election_tree = etree.fromstring(root_string)
    duplicate_validator = rules.DuplicateContestNames(election_tree, None)
    with self.assertRaises(base.ElectionTreeError):
      duplicate_validator.check()


class ValidStableIDTest(absltest.TestCase):

  def setUp(self):
    super(ValidStableIDTest, self).setUp()
    self.root_string = """
        <ExternalIdentifier>
          <Type>{}</Type>
          {}
          <Value>{}</Value>
        </ExternalIdentifier>
    """
    self.stable_string = "<OtherType>stable</OtherType>"
    self.stable_id_validator = rules.ValidStableID(None, None)

  def testValidStableID(self):

    test_string = self.root_string.format("other", self.stable_string,
                                          "vageneral-cand-2013-va-obama")
    self.stable_id_validator.check(etree.fromstring(test_string))

  def testNonStableIDOtherTypesDontThrowError(self):

    test_string = self.root_string.format("other",
                                          "<OtherType>anothertype</OtherType>",
                                          "vageneral-cand-2013-va-obama")
    self.stable_id_validator.check(etree.fromstring(test_string))

  def testNonStableIDTypesDontThrowError(self):

    test_string = self.root_string.format("ocd-id", "",
                                          "ocd-id/country/state/thing")
    self.stable_id_validator.check(etree.fromstring(test_string))

  def testInvalidStableID(self):

    test_string = self.root_string.format("other", self.stable_string,
                                          "cand-2013-va-obama!")
    with self.assertRaises(base.ElectionError) as cm:
      self.stable_id_validator.check(etree.fromstring(test_string))
    self.assertIn("is not in the correct format.", str(cm.exception))

  def testEmptyStableIDFails(self):

    test_string = self.root_string.format("other", self.stable_string, "   ")
    with self.assertRaises(base.ElectionError) as cm:
      self.stable_id_validator.check(etree.fromstring(test_string))
    self.assertIn("is not in the correct format.", str(cm.exception))


class CheckIdentifiersTest(absltest.TestCase):

  _base_report = """
    <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <Contest objectId="cc11111">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Value>{}</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Contest>
      <Candidate objectId="cc22222">
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Value>{}</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Candidate>
      <Party objectId="cc33333">
        {}
      </Party>
      <Office>
        My cool office
      </Office>
    </ElectionReport>
  """

  def testCandidateContestPartyElementsHaveExternalIds(self):
    party_external_ids = """
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Value>party id</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """
    root_string = self._base_report.format("contest id", "candidate id",
                                           party_external_ids)
    election_tree = etree.fromstring(root_string)

    rules.CheckIdentifiers(election_tree, None).check()

  def testIgnoresExternalIdentifiersForContestStages(self):
    contest_stages = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <Contest objectId="cc11111">
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>contest-stage</OtherType>
              <Value>projections</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </Contest>
        <Contest objectId="cc22222">
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>contest-stage</OtherType>
              <Value>projections</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </Contest>
      </ElectionReport>
    """
    election_tree = etree.fromstring(contest_stages)
    rules.CheckIdentifiers(election_tree, None).check()

  def testRaisesErrorIfExternalIdentifiersMissing(self):
    root_string = self._base_report.format("contest id", "candidate id", "")
    election_tree = etree.fromstring(root_string)

    with self.assertRaises(base.ElectionTreeError):
      rules.CheckIdentifiers(election_tree, None).check()

  def testRaisesErrorIfExternalIdentifierMissing(self):
    root_string = self._base_report.format("contest id", "candidate id",
                                           "<ExternalIdentifiers/>")
    election_tree = etree.fromstring(root_string)

    with self.assertRaises(base.ElectionTreeError):
      rules.CheckIdentifiers(election_tree, None).check()

  def testRaisesErrorIfValueMissing(self):
    party_external_ids = """
      <ExternalIdentifiers>
        <ExternalIdentifier/>
      </ExternalIdentifiers>
    """
    root_string = self._base_report.format("contest id", "candidate id",
                                           party_external_ids)
    election_tree = etree.fromstring(root_string)

    with self.assertRaises(base.ElectionTreeError):
      rules.CheckIdentifiers(election_tree, None).check()

  def testRaisesErrorIfDuplicateExternalIdValues(self):
    party_external_ids = """
      <ExternalIdentifiers>
        <ExternalIdentifier>
          <Value>party id</Value>
        </ExternalIdentifier>
      </ExternalIdentifiers>
    """
    root_string = self._base_report.format("this id rocks", "this id rocks",
                                           party_external_ids)
    election_tree = etree.fromstring(root_string)

    with self.assertRaises(base.ElectionTreeError):
      rules.CheckIdentifiers(election_tree, None).check()


class OfficeMissingOfficeHolderPersonDataTest(absltest.TestCase):

  # _gather_reference_values tests
  def testReturnsOfficeHolderPersonIdsFromOfficeCollection(self):
    root_string = """
      <xml>
        <OfficeCollection>
          <Office><OfficeHolderPersonIds>p1 p2</OfficeHolderPersonIds></Office>
          <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
        </OfficeCollection>
      </xml>
    """
    tree = etree.ElementTree(etree.fromstring(root_string))
    office_validator = rules.OfficeMissingOfficeHolderPersonData(tree, None)

    reference_values = office_validator._gather_reference_values()
    expected_reference_values = set(["p1", "p2", "p3"])
    self.assertEqual(expected_reference_values, reference_values)

  # _gather_defined_values tests
  def testReturnsObjectIdsFromPersonCollectionPeople(self):
    root_string = """
      <xml>
        <PersonCollection>
          <Person objectId="p1"/>
          <Person objectId="p2">
            <PartyId>par1</PartyId>
          </Person>
          <Person objectId="p3"/>
        </PersonCollection>
      </xml>
    """
    tree = etree.ElementTree(etree.fromstring(root_string))
    office_validator = rules.OfficeMissingOfficeHolderPersonData(tree, None)

    reference_values = office_validator._gather_defined_values()
    expected_reference_values = set(["p1", "p2", "p3"])
    self.assertEqual(expected_reference_values, reference_values)

  # check tests
  def testCheckEachOfficeHasHolderWithValidPersonId(self):
    root_string = io.BytesIO(b"""
      <xml>
        <OfficeCollection>
          <Office><OfficeHolderPersonIds>p1 p2</OfficeHolderPersonIds></Office>
          <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
        </OfficeCollection>
        <PersonCollection>
          <Person objectId="p1"/>
          <Person objectId="p2">
            <PartyId>par1</PartyId>
          </Person>
          <Person objectId="p3"/>
        </PersonCollection>
      </xml>
    """)
    tree = etree.parse(root_string)
    office_validator = rules.OfficeMissingOfficeHolderPersonData(tree, None)
    office_validator.check()

  def testRaisesErrorIfOfficeHolderIdHasNoMatchingPersonElement(self):
    root_string = io.BytesIO(b"""
      <xml>
        <OfficeCollection>
          <Office><OfficeHolderPersonIds>p1 p2</OfficeHolderPersonIds></Office>
          <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
        </OfficeCollection>
        <PersonCollection>
          <Person objectId="p2">
            <PartyId>par1</PartyId>
          </Person>
          <Person objectId="p3"/>
        </PersonCollection>
      </xml>
    """)
    tree = etree.parse(root_string)
    office_validator = rules.OfficeMissingOfficeHolderPersonData(tree, None)

    with self.assertRaises(base.ElectionError) as ee:
      office_validator.check()
    self.assertIn("No defined Person for p1 found in the feed.",
                  str(ee.exception))

  def testRaisesErrorIfNoPersonCollectionIsPresent(self):
    root_string = io.BytesIO(b"""
      <xml>
        <OfficeCollection>
          <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
        </OfficeCollection>
      </xml>
    """)
    tree = etree.parse(root_string)
    office_validator = rules.OfficeMissingOfficeHolderPersonData(tree, None)

    with self.assertRaises(base.ElectionError) as ee:
      office_validator.check()
    self.assertIn("No defined Person for p3 found in the feed.",
                  str(ee.exception))

  def testRaisesErrorIfOfficeHolderHasNoId(self):
    root_string = io.BytesIO(b"""
      <xml>
        <OfficeCollection>
          <Office><OfficeHolderPersonIds>p1 p2</OfficeHolderPersonIds></Office>
          <Office><OfficeHolderPersonIds>  </OfficeHolderPersonIds></Office>
        </OfficeCollection>
        <PersonCollection>
          <Person objectId="p1"/>
          <Person objectId="p2">
            <PartyId>par1</PartyId>
          </Person>
        </PersonCollection>
      </xml>
    """)
    tree = etree.parse(root_string)
    office_validator = rules.OfficeMissingOfficeHolderPersonData(tree, None)

    with self.assertRaises(base.ElectionError) as ee:
      office_validator.check()
    self.assertIn("Office is missing IDs of Officeholders.", str(ee.exception))

  def testIgnoresTreesWithNoRoot(self):
    no_root_string = io.BytesIO(b"""
      <OfficeCollection/>
    """)
    election_tree = etree.parse(no_root_string)
    rules.OfficeMissingOfficeHolderPersonData(election_tree, None).check()


class PersonsMissingPartyDataTest(absltest.TestCase):

  def setUp(self):
    super(PersonsMissingPartyDataTest, self).setUp()
    self.party_validator = rules.PersonsMissingPartyData(None, None)

  def testChecksPersonElements(self):
    self.assertEqual(["Person"], self.party_validator.elements())

  def testGivenPersonElementHasPartyIdWithAValueInIt(self):
    element_string = """
      <Person objectId="p1">
        <PartyId>par1</PartyId>
      </Person>
    """
    self.party_validator.check(etree.fromstring(element_string))

  def testRaisesErrorForMissingOrEmptyPartyId(self):
    element_string = """
      <Person objectId="p1">
        <PartyId></PartyId>
      </Person>
    """

    with self.assertRaises(base.ElectionWarning):
      self.party_validator.check(etree.fromstring(element_string))


class AllCapsTest(absltest.TestCase):

  def setUp(self):
    super(AllCapsTest, self).setUp()
    self.caps_validator = rules.AllCaps(None, None)

  def testOnlyChecksListedElements(self):
    expected_elements = [
        "Candidate", "CandidateContest", "PartyContest", "Person"
    ]

    self.assertEqual(expected_elements, self.caps_validator.elements())

  def testMakesSureCandidateBallotNamesAreNotAllCapsIfTheyExist(self):
    candidate_string = """
      <Candidate>
        <BallotName>
          <Text>Deandra Reynolds</Text>
        </BallotName>
      </Candidate>
    """
    element = etree.fromstring(candidate_string)

    self.caps_validator.check(element)

  def testIgnoresCandidateElementsWithNoBallotName(self):
    no_ballot_name_string = """
      <Candidate/>
    """
    element = etree.fromstring(no_ballot_name_string)

    self.caps_validator.check(element)

  def testIgnoresCandidateElementsWithNoText(self):
    no_text_string = """
      <Candidate>
        <BallotName/>
      </Candidate>
    """
    element = etree.fromstring(no_text_string)

    self.caps_validator.check(element)

  def testRaisesWarningIfCandidateBallotNameIsAllCaps(self):
    candidate_string = """
      <Candidate>
        <BallotName>
          <Text>DEANDRA REYNOLDS</Text>
        </BallotName>
      </Candidate>
    """
    element = etree.fromstring(candidate_string)

    with self.assertRaises(base.ElectionWarning):
      self.caps_validator.check(element)

  def testMakesSureContestNamesAreNotAllCapsIfTheyExist(self):
    contest_string = """
      <Contest>
        <Name>Deandra Reynolds</Name>
      </Contest>
    """
    element = etree.fromstring(contest_string)

    self.caps_validator.check(element)

  def testIgnoresContestElementsWithNoName(self):
    no_name_string = """
      <Contest/>
    """
    element = etree.fromstring(no_name_string)

    self.caps_validator.check(element)

  def testRaisesWarningIfContestNameIsAllCaps(self):
    contest_string = """
      <Contest>
        <Name>DEANDRA REYNOLDS</Name>
      </Contest>
    """
    element = etree.fromstring(contest_string)

    with self.assertRaises(base.ElectionWarning):
      self.caps_validator.check(element)

  def testMakesSureFullNamesAreNotAllCapsIfTheyExist(self):
    party_contest_string = """
      <PartyContest>
        <FullName>
          <Text>World's Cutest Dog</Text>
        </FullName>
      </PartyContest>
    """
    element = etree.fromstring(party_contest_string)

    self.caps_validator.check(element)

  def testIgnoresPersonElementsWithNoFullName(self):
    no_full_name_string = """
      <Person/>
    """
    element = etree.fromstring(no_full_name_string)

    self.caps_validator.check(element)

  def testIgnoresPersonElementsWithNoText(self):
    no_text_string = """
      <Person>
        <FullName/>
      </Person>
    """
    element = etree.fromstring(no_text_string)

    self.caps_validator.check(element)

  def testRaisesWarningIfFullNamesAreAllCaps_PartyContest(self):
    party_contest_string = """
      <PartyContest>
        <FullName>
          <Text>DEANDRA REYNOLDS</Text>
        </FullName>
      </PartyContest>
    """
    element = etree.fromstring(party_contest_string)

    with self.assertRaises(base.ElectionWarning):
      self.caps_validator.check(element)

  def testRaisesWarningIfFullNamesAreAllCaps_Person(self):
    person_string = """
      <Person>
        <FullName>
          <Text>DEANDRA REYNOLDS</Text>
        </FullName>
      </Person>
    """
    element = etree.fromstring(person_string)

    with self.assertRaises(base.ElectionWarning):
      self.caps_validator.check(element)


class AllLanguagesTest(absltest.TestCase):

  def setUp(self):
    super(AllLanguagesTest, self).setUp()
    self.language_validator = rules.AllLanguages(None, None)

  def testOnlyChecksListedElements(self):
    expected_elements = ["BallotName", "BallotTitle", "FullName", "Name"]
    self.assertEqual(expected_elements, self.language_validator.elements())

  def testGivenElementHasTextForEachRequiredLanguage(self):
    root_string = """
      <FullName>
        <Text language="en">Name</Text>
        <Text language="es">Nombre</Text>
        <Text language="nl">Naam</Text>
      </FullName>
    """
    self.language_validator.required_languages = ["en", "es", "nl"]
    self.language_validator.check(etree.fromstring(root_string))

  def testGivenElementCanSupportMoreThanRequiredLanguages(self):
    root_string = """
      <FullName>
        <Text language="en">Name</Text>
        <Text language="es">Nombre</Text>
        <Text language="nl">Naam</Text>
      </FullName>
    """
    self.language_validator.required_languages = ["en"]
    self.language_validator.check(etree.fromstring(root_string))

  def testRaisesAnErrorIfRequiredLanguageIsMissing(self):
    root_string = """
      <FullName>
        <Text language="en">Name</Text>
        <Text language="es">Nombre</Text>
      </FullName>
    """
    self.language_validator.required_languages = ["en", "es", "nl"]
    with self.assertRaises(base.ElectionError):
      self.language_validator.check(etree.fromstring(root_string))

  def testIgnoresElementsWithoutTextElements(self):
    empty_element_string = """
      <BallotName/>
    """
    self.language_validator.check(etree.fromstring(empty_element_string))


class ValidEnumerationsTest(absltest.TestCase):

  def setUp(self):
    super(ValidEnumerationsTest, self).setUp()
    self.enum_validator = rules.ValidEnumerations(None, None)

  def testElementsGathersValidEnumerationsAndReturnsElementsWithOtherType(self):
    schema_file = io.BytesIO(b"""<?xml version="1.0" encoding="UTF-8"?>
      <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="Report"/>
        <xs:simpleType name="BallotMeasureType">
          <xs:restriction base="xs:string">
              <xs:enumeration value="ballot-measure" />
              <xs:enumeration value="initiative" />
              <xs:enumeration value="referendum" />
              <xs:enumeration value="other" />
          </xs:restriction>
        </xs:simpleType>
        <xs:complexType name="Person">
          <xs:sequence>
            <xs:element minOccurs="1" type="xs:string" name="FirstName" />
            <xs:element minOccurs="1" type="xs:string" name="LastName" />
            <xs:element minOccurs="0" type="xs:integer" name="Age" />
            <xs:element minOccurs="0" type="xs:string" name="OtherType" />
          </xs:sequence>
        </xs:complexType>
      </xs:schema>
    """)
    enum_validator = rules.ValidEnumerations(None, schema_file)
    expected_enumerations = ["ballot-measure", "initiative", "referendum"]
    expected_elements = ["Person"]

    elements = enum_validator.elements()
    self.assertEqual(expected_enumerations, enum_validator.valid_enumerations)
    self.assertEqual(expected_elements, elements)

  def testElementsOfTypeOtherDoNotUseValidEnumerationInOtherTypeField(self):
    type_other_string = """
    <GpUnit objectId="ru0002">
      <Name>Virginia</Name>
      <Type>state</Type>
    </GpUnit>
    """
    element = etree.fromstring(type_other_string)
    self.enum_validator.valid_enumerations = ["state"]
    self.enum_validator.check(element)

  def testRaisesAnErrorIfOtherTypeFieldHasValidEnumerationAsAValue(self):
    type_other_string = """
    <GpUnit objectId="ru0002">
      <Name>Virginia</Name>
      <Type>other</Type>
      <OtherType>state</OtherType>
    </GpUnit>
    """
    element = etree.fromstring(type_other_string)
    self.enum_validator.valid_enumerations = ["state"]
    with self.assertRaises(base.ElectionError):
      self.enum_validator.check(element)

  def testElementsOfTypeOtherForExternalIdentifierElements(self):
    type_other_string = """
      <ExternalIdentifier>
        <Type>stable</Type>
        <Value>Paddy's Pub</Value>
      </ExternalIdentifier>
    """
    element = etree.fromstring(type_other_string)
    self.enum_validator.valid_enumerations = ["stable"]
    self.enum_validator.check(element)

  def testExternalIdentifierForValidEnumerationSetAsOtherType(self):
    type_other_string = """
      <ExternalIdentifier>
        <Type>other</Type>
        <OtherType>stable</OtherType>
        <Value>Paddy's Pub</Value>
      </ExternalIdentifier>
    """
    element = etree.fromstring(type_other_string)
    self.enum_validator.valid_enumerations = ["stable"]
    with self.assertRaises(base.ElectionError):
      self.enum_validator.check(element)

  def testIgnoresElementsWithNoTypeOrOtherType(self):
    no_type_string = """
      <ExternalIdentifier>
        <Value>Paddy's Pub</Value>
      </ExternalIdentifier>
    """
    element = etree.fromstring(no_type_string)

    self.enum_validator.check(element)

    no_other_type_string = """
      <ExternalIdentifier>
        <Type>other</Type>
        <Value>Paddy's Pub</Value>
      </ExternalIdentifier>
    """
    element = etree.fromstring(no_other_type_string)

    self.enum_validator.check(element)


class ValidateOcdidLowerCaseTest(absltest.TestCase):

  def setUp(self):
    super(ValidateOcdidLowerCaseTest, self).setUp()
    self.ocdid_validator = rules.ValidateOcdidLowerCase(None, None)

  def testItChecksExternalIdentifierElements(self):
    self.assertEqual(["ExternalIdentifier"], self.ocdid_validator.elements())

  def testItMakesSureOcdidsAreAllLowerCase(self):
    valid_id_string = """
      <ExternalIdentifier>
        <Type>ocd-id</Type>
        <Value>ocd-division/country:us/state:va</Value>
      </ExternalIdentifier>
    """
    self.ocdid_validator.check(etree.fromstring(valid_id_string))

  def testRaisesWarningIfOcdidHasUpperCaseLetter(self):
    uppercase_string = """
      <ExternalIdentifier>
        <Type>ocd-id</Type>
        <Value>ocd-division/country:us/state:VA</Value>
      </ExternalIdentifier>
    """
    with self.assertRaises(base.ElectionWarning) as ew:
      self.ocdid_validator.check(etree.fromstring(uppercase_string))
    self.assertIn("Valid OCD-IDs should be all lowercase", str(ew.exception))

  def testIgnoresElementsWithoutValidOcdidXml(self):
    no_type_string = """
      <ExternalIdentifier/>
    """
    self.ocdid_validator.check(etree.fromstring(no_type_string))

    non_ocdid_string = """
      <ExternalIdentifier>
        <Type>not-ocdid</Type>
      </ExternalIdentifier>
    """
    self.ocdid_validator.check(etree.fromstring(non_ocdid_string))

    ocdid_missing_value_string = """
      <ExternalIdentifier>
        <Type>ocd-id</Type>
      </ExternalIdentifier>
    """
    self.ocdid_validator.check(etree.fromstring(ocdid_missing_value_string))

    empty_value_string = """
      <ExternalIdentifier>
        <Type>ocd-id</Type>
        <Value></Value>
      </ExternalIdentifier>
    """
    self.ocdid_validator.check(etree.fromstring(empty_value_string))


class ContestHasMultipleOfficesTest(absltest.TestCase):

  base_string = """<Contest>{}</Contest>"""

  def setUp(self):
    super(ContestHasMultipleOfficesTest, self).setUp()
    self.contest_offices_validator = rules.ContestHasMultipleOffices(None, None)

  def testOneOfficeValid(self):
    root_string = self.base_string.format("<OfficeIds>off-ar1-arb</OfficeIds>")
    element = etree.fromstring(root_string)
    self.contest_offices_validator.check(element)

  def testMultipleOfficesFail(self):
    root_string = self.base_string.format(
        "<OfficeIds>off-ar1-ara off-ar1-arb</OfficeIds>")
    element = etree.fromstring(root_string)

    with self.assertRaises(base.ElectionError) as cm:
      self.contest_offices_validator.check(element)
    self.assertIn("has more than one associated office.", str(cm.exception))

  def testNoOfficesFail(self):
    root_string = self.base_string.format("<OfficeIds></OfficeIds>")
    element = etree.fromstring(root_string)

    with self.assertRaises(base.ElectionError) as cm:
      self.contest_offices_validator.check(element)
    self.assertIn("has no associated offices.", str(cm.exception))


class PersonHasOfficeTest(absltest.TestCase):

  _base_xml = """
    <xml>
      <PersonCollection>
        <Person objectId="p1" />
        <Person objectId="p2" />
        <Person objectId="p3" />
      </PersonCollection>
      {}
    </xml>
  """

  # _gather_reference_values tests
  def testReturnsPersonIdsFromPersonCollection(self):
    root_string = self._base_xml.format("")
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    office_validator = rules.PersonHasOffice(election_tree, None)

    reference_values = office_validator._gather_reference_values()
    expected_reference_values = set(["p1", "p2", "p3"])
    self.assertEqual(expected_reference_values, reference_values)

  # _gather_defined_values tests
  def testReturnsPartyLeaderAndOfficeHolderIds(self):
    defined_collections = """
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p2</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
      </OfficeCollection>
      <PartyCollection>
        <Party>
          <ExternalIdentifiers>
            <ExternalIdentifier>
              <Type>other</Type>
              <OtherType>party-leader-id</OtherType>
              <Value>p4</Value>
            </ExternalIdentifier>
          </ExternalIdentifiers>
        </Party>
      </PartyCollection>
    """
    root_string = self._base_xml.format(defined_collections)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    office_validator = rules.PersonHasOffice(election_tree, None)

    defined_values = office_validator._gather_defined_values()
    expected_defined_values = set(["p1", "p2", "p3", "p4"])
    self.assertEqual(expected_defined_values, defined_values)

  # check tests
  def testEachPersonInACollectionIsReferencedByAnOffice(self):
    office_collection = """
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p2</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p3</OfficeHolderPersonIds></Office>
      </OfficeCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode()))
    election_tree = etree.parse(root_string)
    office_validator = rules.PersonHasOffice(election_tree, None)
    office_validator.check()

  def testIgnoresTreesWithNoRoots(self):
    no_root_string = io.BytesIO(b"<OfficeCollection/>")
    election_tree = etree.parse(no_root_string)
    office_validator = rules.PersonHasOffice(election_tree, None)
    office_validator.check()

  def testIgnoresRootsWithNoPersonCollection(self):
    no_collection_string = io.BytesIO(b"""
      <xml>
        <OfficeCollection/>
      </xml>
    """)
    election_tree = etree.parse(no_collection_string)
    office_validator = rules.PersonHasOffice(election_tree, None)
    office_validator.check()

  def testRaisesErrorIfPersonIsNotReferencedInAnyOffice(self):
    office_collection = """
      <OfficeCollection>
        <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        <Office><OfficeHolderPersonIds>p2</OfficeHolderPersonIds></Office>
        <Office/>
      </OfficeCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode()))
    election_tree = etree.parse(root_string)
    office_validator = rules.PersonHasOffice(election_tree, None)
    with self.assertRaises(base.ElectionError):
      office_validator.check()

  def testRaisesErrorIfTheresAPersonCollectionButNoOfficeCollection(self):
    root_string = io.BytesIO(bytes(self._base_xml.encode()))
    election_tree = etree.parse(root_string)
    office_validator = rules.PersonHasOffice(election_tree, None)
    with self.assertRaises(base.ElectionError):
      office_validator.check()

  def testPartyLeadersDoNotRequireOffices(self):
    office_party_collections = """
      <OfficeCollection>
          <Office><OfficeHolderPersonIds>p1</OfficeHolderPersonIds></Office>
        </OfficeCollection>
        <PartyCollection>
          <Party>
            <Name>Republican Socialists</Name>
            <ExternalIdentifiers>
              <ExternalIdentifier>
                <Type>Other</Type>
                <OtherType>party-leader-id</OtherType>
                <Value>p2</Value>
              </ExternalIdentifier>
              <ExternalIdentifier>
                <Type>Other</Type>
                <OtherType>party-chair-id</OtherType>
                <Value>p3</Value>
              </ExternalIdentifier>
            </ExternalIdentifiers>
          </Party>
        </PartyCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_party_collections).encode()))
    election_tree = etree.parse(root_string)
    office_validator = rules.PersonHasOffice(election_tree, None)
    office_validator.check()

  def testPersonHasOneOffice(self):
    # NOTE: That all offices have valid Persons is
    # checked by testOfficeMissingOfficeHolderPersonData
    office_collection = """
      <OfficeCollection>
        <Office objectId="o1">
          <OfficeHolderPersonIds>p1</OfficeHolderPersonIds>
        </Office>
        <Office objectId="o2">
          <OfficeHolderPersonIds>p2</OfficeHolderPersonIds>
        </Office>
        <Office objectId="o3">
          <OfficeHolderPersonIds>p3</OfficeHolderPersonIds>
        </Office>
        <Office objectId="o4">
          <OfficeHolderPersonIds>p4</OfficeHolderPersonIds>
        </Office>
      </OfficeCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode()))
    election_tree = etree.parse(root_string)
    rules.PersonHasOffice(election_tree, None).check()

  def testPersonHasOneOffice_fails(self):
    office_collection = """
      <OfficeCollection>
        <Office objectId="o1">
          <OfficeHolderPersonIds>p1</OfficeHolderPersonIds>
        </Office>
        <Office objectId="o2">
          <OfficeHolderPersonIds>p2</OfficeHolderPersonIds>
        </Office>
      </OfficeCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode()))
    election_tree = etree.parse(root_string)

    with self.assertRaises(base.ElectionError) as cm:
      rules.PersonHasOffice(election_tree, None).check()

    self.assertIn("No defined data for p3 found in the feed.",
                  str(cm.exception))

  def testOfficeHasOnePerson_fails(self):
    office_collection = """
      <OfficeCollection>
        <Office objectId="o1">
           <OfficeHolderPersonIds>p1</OfficeHolderPersonIds>
        </Office>
        <Office objectId="o2">
           <OfficeHolderPersonIds>p2 p3</OfficeHolderPersonIds>
        </Office>
      </OfficeCollection>
    """
    root_string = io.BytesIO(
        bytes(self._base_xml.format(office_collection).encode()))
    election_tree = etree.parse(root_string)

    with self.assertRaises(base.ElectionError) as cm:
      rules.PersonHasOffice(election_tree, None).check()

    self.assertIn("OfficeHolders. Must have exactly one.", str(cm.exception))


class PartyLeadershipMustExistTest(absltest.TestCase):

  _party_collection = """
    <PartyCollection>
      <Party>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>Other</Type>
            <OtherType>party-leader-id</OtherType>
            <Value>p2</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Party>
      <Party>
        <ExternalIdentifiers>
          <ExternalIdentifier>
            <Type>Other</Type>
            <OtherType>party-chair-id</OtherType>
            <Value>p3</Value>
          </ExternalIdentifier>
        </ExternalIdentifiers>
      </Party>
    </PartyCollection>
  """

  # _gather_reference_values tests
  def testReturnsSetOfPartyLeaderIds(self):
    root_string = """
      <xml>
        <PersonCollection>
          <Person objectId="p2" />
          <Person objectId="p3" />
        </PersonCollection>
        {}
      </xml>
    """.format(self._party_collection)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    leadership_validator = rules.PartyLeadershipMustExist(election_tree, None)

    reference_values = leadership_validator._gather_reference_values()
    expected_reference_values = set(["p2", "p3"])
    self.assertEqual(expected_reference_values, reference_values)

  # _gather_defined_values tests
  def testReturnsSetOfPersonObjectIds(self):
    root_string = """
      <xml>
        <PersonCollection>
          <Person objectId="p4" />
          <Person objectId="p5" />
        </PersonCollection>
        {}
      </xml>
    """.format(self._party_collection)
    election_tree = etree.ElementTree(etree.fromstring(root_string))
    leadership_validator = rules.PartyLeadershipMustExist(election_tree, None)

    defined_values = leadership_validator._gather_defined_values()
    expected_defined_values = set(["p4", "p5"])
    self.assertEqual(expected_defined_values, defined_values)

  # check tests
  def testPartyLeadershipExists(self):
    xml_string = """
      <xml>
        <PersonCollection>
          <Person objectId="p2" />
          <Person objectId="p3" />
        </PersonCollection>
        {}
      </xml>
    """.format(self._party_collection)
    root_string = io.BytesIO(bytes(xml_string.encode()))
    election_tree = etree.parse(root_string)
    rules.PartyLeadershipMustExist(election_tree, None).check()

  def testPartyLeadershipExists_fails(self):
    xml_string = """
      <xml>
        {}
      </xml>
    """.format(self._party_collection)
    root_string = io.BytesIO(bytes(xml_string.encode()))
    with self.assertRaises(base.ElectionError):
      election_tree = etree.parse(root_string)
      rules.PartyLeadershipMustExist(election_tree, None).check()


class ProhibitElectionDataTest(absltest.TestCase):

  def testElectionElementIsNotPresent(self):
    root_string = io.BytesIO(b"""
      <xml>
        <PersonCollection/>
      </xml>
    """)
    election_tree = etree.parse(root_string)
    rules.ProhibitElectionData(election_tree, None).check()

  def testRaisesErrorIfElectionElementIsPresent(self):
    root_string = io.BytesIO(b"""
      <xml>
        <Election/>
      </xml>
    """)
    election_tree = etree.parse(root_string)
    with self.assertRaises(base.ElectionError) as ee:
      rules.ProhibitElectionData(election_tree, None).check()
    self.assertIn("Election data is prohibited", str(ee.exception))


class PersonsHaveValidGenderTest(absltest.TestCase):

  def setUp(self):
    super(PersonsHaveValidGenderTest, self).setUp()
    self.gender_validator = rules.PersonsHaveValidGender(None, None)

  def testOnlyGenderElementsAreChecked(self):
    self.assertEqual(["Gender"], self.gender_validator.elements())

  def testAllPersonsHaveValidGender(self):
    root_string = """
      <Gender>Female</Gender>
    """
    gender_element = etree.fromstring(root_string)
    self.gender_validator.check(gender_element)

  def testValidationIsCaseInsensitive(self):
    root_string = """
      <Gender>female</Gender>
    """
    gender_element = etree.fromstring(root_string)
    self.gender_validator.check(gender_element)

  def testValidationIgnoresEmptyValue(self):
    root_string = """
      <Gender></Gender>
    """
    gender_element = etree.fromstring(root_string)
    self.gender_validator.check(gender_element)

  def testValidationFailsForInvalidValue(self):
    root_string = """
      <Gender>blamo</Gender>
    """
    gender_element = etree.fromstring(root_string)
    with self.assertRaises(base.ElectionError):
      self.gender_validator.check(gender_element)


class VoteCountTypesCoherencyTest(absltest.TestCase):

  def setUp(self):
    super(VoteCountTypesCoherencyTest, self).setUp()
    self.vc_coherency = rules.VoteCountTypesCoherency(None, None)
    self.base_contest = """
      <Contest objectId="pc1" type="{}">
        <BallotSelection objectId="ps1-0">
          <VoteCountsCollection>
            {}
          </VoteCountsCollection>
        </BallotSelection>
      </Contest>
    """

  def testInvalidNotInPartyContest(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>seats-leading</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>0.0</Count>
      </VoteCounts>
    """
    contest = self.base_contest.format("PartyContest", vote_counts)
    self.vc_coherency.check(etree.fromstring(contest))

  def testInvalidNotInPartyContest_fails(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>candidate-votes</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>0.0</Count>
      </VoteCounts>
    """
    contest = self.base_contest.format("PartyContest", vote_counts)
    with self.assertRaises(base.ElectionError) as cm:
      self.vc_coherency.check(etree.fromstring(contest))

    for vc_type in rules.VoteCountTypesCoherency.CAND_VC_TYPES:
      self.assertIn(vc_type, str(cm.exception))

  def testInvalidNotInCandidateContest(self):
    vote_counts = """
      <VoteCounts>
        <OtherType>candidate-votes</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>0.0</Count>
      </VoteCounts>
    """
    contest = self.base_contest.format("CandidateContest", vote_counts)
    self.vc_coherency.check(etree.fromstring(contest))

  def testNonInvalidVCTypesDoNotFail(self):
    # returns None if no VoteCount types
    vote_counts = """
      <VoteCounts>
        <OtherType>total-percent</OtherType>
        <Count>0.0</Count>
      </VoteCounts>
      <VoteCounts>
        <OtherType>some-future-vote-count-type</OtherType>
      </VoteCounts>
    """
    contest = self.base_contest.format("CandidateContest", vote_counts)
    self.assertIsNone(self.vc_coherency.check(etree.fromstring(contest)))

  def testInvalidNotInCandidateContest_fails(self):
    # Checks Candidate parsing fails on all party types
    vote_counts = """
      <VoteCounts>
        <OtherType>seats-won</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>seats-leading</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>party-votes</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>seats-no-election</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>seats-total</OtherType>
      </VoteCounts>
      <VoteCounts>
        <OtherType>seats-delta</OtherType>
      </VoteCounts>
    """
    contest = self.base_contest.format("CandidateContest", vote_counts)

    with self.assertRaises(base.ElectionError) as cm:
      self.vc_coherency.check(etree.fromstring(contest))

    for vc_type in rules.VoteCountTypesCoherency.PARTY_VC_TYPES:
      self.assertIn(vc_type, str(cm.exception))


class URIValidatorTest(absltest.TestCase):

  def setUp(self):
    super(URIValidatorTest, self).setUp()
    self.uri_validator = rules.URIValidator(None, None)
    self.uri_element = u"<Uri>{}</Uri>"

  def testOnlyChecksUriElements(self):
    self.assertEqual(["Uri"], self.uri_validator.elements())

  def testChecksForValidUri(self):
    valid_url = self.uri_element.format("http://www.whitehouse.gov")
    self.uri_validator.check(etree.fromstring(valid_url))

  def testChecksForValidNonWwwUri(self):
    valid_url = self.uri_element.format(
        "https://zh.wikipedia.org/zh-tw/Fake_Page")
    self.uri_validator.check(etree.fromstring(valid_url))

  def testChecksForValidUriWithParentheses(self):
    valid_url = self.uri_element.format(
        "http://en.wikipedia.org/wiki/Thomas_Jefferson_(Virginia)")
    self.uri_validator.check(etree.fromstring(valid_url))

  def testRaisesAnErrorIfUriNotProvided(self):
    invalid_scheme = self.uri_element.format("")
    with self.assertRaises(base.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(invalid_scheme))
    self.assertIn("Missing URI value.", str(ee.exception))

  def testRaisesAnErrorIfNoSchemeProvided(self):
    missing_scheme = self.uri_element.format("www.whitehouse.gov")
    with self.assertRaises(base.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(missing_scheme))
    self.assertIn("protocol - invalid", str(ee.exception))

  def testRaisesAnErrorIfSchemeIsNotInApprovedList(self):
    invalid_scheme = self.uri_element.format("tps://www.whitehouse.gov")
    with self.assertRaises(base.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(invalid_scheme))
    self.assertIn("protocol - invalid", str(ee.exception))

  def testRaisesAnErrorIfNetLocationNotProvided(self):
    missing_netloc = self.uri_element.format("missing/loc.md")
    with self.assertRaises(base.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(missing_netloc))
    self.assertIn("domain - missing", str(ee.exception))

  def testRaisesAnErrorIfUriNotAscii(self):
    unicode_url = self.uri_element.format(u"https://nahnah.com/nopê")
    with self.assertRaises(base.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(unicode_url))
    self.assertIn("not ascii encoded", str(ee.exception))

  def testAllowsQueryParamsToBeIncluded(self):
    contains_query = self.uri_element.format(
        "http://www.whitehouse.gov?filter=yesplease")
    self.uri_validator.check(etree.fromstring(contains_query))

  def testAggregatesErrors(self):
    multiple_issues = self.uri_element.format("missing/loc.md?filter=yesplease")
    with self.assertRaises(base.ElectionError) as ee:
      self.uri_validator.check(etree.fromstring(multiple_issues))
    self.assertIn("protocol - invalid", str(ee.exception))
    self.assertIn("domain - missing", str(ee.exception))


class ValidURIAnnotationTest(absltest.TestCase):

  def setUp(self):
    super(ValidURIAnnotationTest, self).setUp()
    self.valid_annotation = rules.ValidURIAnnotation(None, None)

  def testOnlyChecksContactInformationElements(self):
    self.assertEqual(["ContactInformation"], self.valid_annotation.elements())

  def testPlatformOnlyValidAnnotation(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="wikipedia">
          <![CDATA[https://de.wikipedia.org/]]>
        </Uri>
        <Uri Annotation="ballotpedia">
          <![CDATA[http://ballotpedia.org/George_Washington]]>
        </Uri>
        <Uri Annotation="candidate-image">
          <![CDATA[https://www.parlament.gv.at/test.jpg]]>
        </Uri>
      </ContactInformation>
    """
    self.valid_annotation.check(etree.fromstring(root_string))

  def testWikipediaAlternateWritingSystem(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="wikipedia">
          <![CDATA[https://zh.wikipedia.org/zh-cn/Fake_Page]]>
        </Uri>
      </ContactInformation>
    """
    self.valid_annotation.check(etree.fromstring(root_string))

  def testTypePlatformValidAnnotation(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="official-website">
          <![CDATA[https://www.spoe.at]]>
        </Uri>
        <Uri Annotation="official-facebook">
          <![CDATA[https://www.facebook.com]]>
        </Uri>
        <Uri Annotation="official-twitter">
          <![CDATA[https://twitter.com]]>
        </Uri>
        <Uri Annotation="official-youtube">
          <![CDATA[https://www.youtube.com]]>
        </Uri>
        <Uri Annotation="campaign-line">
          <![CDATA[https://line.me/ti/p/@kmtonline]]>
        </Uri>
        <Uri Annotation="personal-instagram">
          <![CDATA[https://www.instagram.com]]>
        </Uri>
        <Uri Annotation="personal-linkedin">
          <![CDATA[https://www.linkedin.com/michael]]>
        </Uri>
      </ContactInformation>
    """
    self.valid_annotation.check(etree.fromstring(root_string))

  def testTypePlatformNoAnnotationWarning(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="official-website">
          <![CDATA[https://www.spoe.at]]>
        </Uri>
        <Uri>
          <![CDATA[https://twitter.com]]>
        </Uri>
      </ContactInformation>
    """
    with self.assertRaises(base.ElectionWarning) as cm:
      self.valid_annotation.check(etree.fromstring(root_string))
    self.assertIn("missing annotation", str(cm.exception))

  def testNoTypeWhenTypePlatformWarning(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="website">
          <![CDATA[https://www.spoe.at]]>
        </Uri>
        <Uri Annotation="official-youtube">
          <![CDATA[https://www.youtube.com]]>
        </Uri>
      </ContactInformation>
    """
    with self.assertRaises(base.ElectionWarning) as cm:
      self.valid_annotation.check(etree.fromstring(root_string))
    self.assertIn("missing usage type.", str(cm.exception))

  def testNoPlatformHasUsageTypeWarning(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="campaign">
          <![CDATA[https://www.spoe.at]]>
        </Uri>
        <Uri Annotation="official-youtube">
          <![CDATA[https://www.youtube.com]]>
        </Uri>
      </ContactInformation>
    """
    with self.assertRaises(base.ElectionError) as cm:
      self.valid_annotation.check(etree.fromstring(root_string))
    self.assertIn("has usage type, missing platform.", str(cm.exception))

  def testIncorrectPlatformFails(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="official-website">
          <![CDATA[https://www.spoe.at]]>
        </Uri>
        <Uri Annotation="personal-twitter">
          <![CDATA[https://www.youtube.com/SmithForGov]]>
        </Uri>
      </ContactInformation>
    """
    with self.assertRaises(base.ElectionError) as cm:
      self.valid_annotation.check(etree.fromstring(root_string))
    self.assertIn("incorrect for URI", str(cm.exception))

  def testNonExistentPlatformFails(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="official-website">
          <![CDATA[https://www.spoe.at]]>
        </Uri>
        <Uri Annotation="campaign-netsite">
          <![CDATA[http://www.smithforgovernor2020.com]]>
        </Uri>
      </ContactInformation>
    """
    with self.assertRaises(base.ElectionWarning) as cm:
      self.valid_annotation.check(etree.fromstring(root_string))
    self.assertIn("is not a valid annotation.", str(cm.exception))

  def testFBAnnotation(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="personal-facebook">
          <![CDATA[https://www.fb.com/juanjomalvinas]]>
        </Uri>
      </ContactInformation>
    """
    self.valid_annotation.check(etree.fromstring(root_string))

  def testIncorrectFBAnnotationFails(self):
    root_string = """
      <ContactInformation label="ci_par_at_1">
        <Uri Annotation="official-fb">
          <![CDATA[https://www.facebook.com]]>
        </Uri>
        <Uri Annotation="personal-fb">
          <![CDATA[http://www.facebook.com]]>
        </Uri>
      </ContactInformation>
    """
    with self.assertRaises(base.ElectionWarning) as cm:
      self.valid_annotation.check(etree.fromstring(root_string))
    self.assertIn("official-fb is not a valid annotation", str(cm.exception))


class OfficesHaveJurisdictionIDTest(absltest.TestCase):

  def setUp(self):
    super(OfficesHaveJurisdictionIDTest, self).setUp()
    self.root_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <OfficeCollection>
          {}
        </OfficeCollection>
      </ElectionReport>
    """
    self.offices_validator = rules.OfficesHaveJurisdictionID(None, None)

  def testOfficeHasJurisdictionIDByAdditionalData(self):
    test_string = self.root_string.format("""
          <Office objectId="off1">
            <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
          </Office>
        """)
    element = etree.fromstring(test_string)
    self.offices_validator.check(element)

  def testOfficeHasJurisdictionIDByExternalIdentifier(self):
    test_string = self.root_string.format("""
          <Office objectId="off1">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>jurisdiction-id</OtherType>
               <Value>ru_pt_999</Value>
             </ExternalIdentifier>
          </Office>
        """)
    element = etree.fromstring(test_string)
    self.offices_validator.check(element)

  def testOfficeDoesNotHaveJurisdictionIDByAdditionalData(self):
    test_string = self.root_string.format("""
          <Office objectId="off2">
            <AdditionalData>ru-gpu4</AdditionalData>
          </Office>
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(base.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("is missing a jurisdiction-id", str(cm.exception))

  def testOfficeDoesNotHaveJurisdictionIDTextByAdditionalData(self):
    test_string = self.root_string.format("""
          <Office objectId="off2">
            <AdditionalData type="jurisdiction-id"></AdditionalData>
          </Office>
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(base.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("is missing a jurisdiction-id", str(cm.exception))

  def testOfficeHasMoreThanOneJurisdictionIDbyAdditionalData(self):
    test_string = self.root_string.format("""
          <Office objectId="off1">
            <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
            <AdditionalData type="jurisdiction-id">ru-gpu3</AdditionalData>
          </Office>
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(base.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("has more than one jurisdiction-id", str(cm.exception))

  def testOfficeDoesNotHaveJurisdictionIDByExternalIdentifier(self):
    test_string = self.root_string.format("""
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <Value>ru-gpu3</Value>
             </ExternalIdentifier>
          </Office>
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(base.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("is missing a jurisdiction-id", str(cm.exception))

  def testOfficeDoesNotHaveJurisdictionIDTextByExternalIdentifier(self):
    test_string = self.root_string.format("""
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>jurisdiction-id</OtherType>
               <Value></Value>
             </ExternalIdentifier>
          </Office>
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(base.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("is missing a jurisdiction-id", str(cm.exception))

  def testOfficeHasMoreThanOneJurisdictionIDbyExternalIdentifier(self):
    test_string = self.root_string.format("""
          <Office objectId="off1">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>jurisdiction-id</OtherType>
               <Value>ru_pt_900</Value>
             </ExternalIdentifier>
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>jurisdiction-id</OtherType>
               <Value>ru_pt_800</Value>
             </ExternalIdentifier>
          </Office>
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(base.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("has more than one jurisdiction-id", str(cm.exception))

  def testJurisdictionIDTextIsWhitespaceByExternalIdentifier(self):
    test_string = self.root_string.format("""
          <Office objectId="off2">
             <ExternalIdentifier>
               <Type>other</Type>
               <OtherType>jurisdiction-id</OtherType>
               <Value>  </Value>
             </ExternalIdentifier>
          </Office>
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(base.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("is missing a jurisdiction-id", str(cm.exception))

  def testJurisdictionIDTextIsWhitespaceByAdditionalData(self):
    test_string = self.root_string.format("""
          <Office objectId="off2">
            <AdditionalData type="jurisdiction-id">    </AdditionalData>
          </Office>
        """)
    element = etree.fromstring(test_string)
    with self.assertRaises(base.ElectionError) as cm:
      self.offices_validator.check(element)
    self.assertIn("is missing a jurisdiction-id", str(cm.exception))


class ValidJurisdictionIDTest(absltest.TestCase):

  def setUp(self):
    super(ValidJurisdictionIDTest, self).setUp()
    self.root_string = """
      <ElectionReport xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <GpUnitCollection>
          {}
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu2"/>
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu3"/>
        </GpUnitCollection>
        <OfficeCollection>
          {}
          <Office objectId="off1">
            <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
          </Office>
          <Office objectId="off2">
            <AdditionalData>ru-gpu4</AdditionalData>
          </Office>
          <Office>
            <ExternalIdentifiers>
              {}
            </ExternalIdentifiers>
          </Office>
        </OfficeCollection>
      </ElectionReport>
    """

  # _gather_reference_values tests
  def testReturnsASetOfJurisdictionIdsFromGivenTree_AdditionalData(self):
    root_string = self.root_string.format(
        "", """
          <Office objectId="off0">
            <AdditionalData type="jurisdiction-id">ru-gpu1</AdditionalData>
          </Office>""", "")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()
    self.assertEqual(set(["ru-gpu1", "ru-gpu2"]), reference_values)

  def testReturnsASetOfJurisdictionIdsFromGivenTree_ExternalIdentifier(self):
    root_string = self.root_string.format(
        "", "", """
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>jurisdiction-id</OtherType>
            <Value>ru-gpu3</Value>
          </ExternalIdentifier>""")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()
    self.assertEqual(set(["ru-gpu2", "ru-gpu3"]), reference_values)

  def testIgnoresExternalIdentifierWithoutType(self):
    root_string = self.root_string.format(
        "", "", """
          <ExternalIdentifier>
            <OtherType>jurisdiction-id</OtherType>
            <Value>ru-gpu3</Value>
          </ExternalIdentifier>""")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()
    self.assertEqual(set(["ru-gpu2"]), reference_values)

  def testIgnoresExternalIdentifierWithoutOtherTypeNotJurisdictionId(self):
    root_string = self.root_string.format(
        "", "", """
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>district-id</OtherType>
            <Value>ru-gpu3</Value>
          </ExternalIdentifier>""")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()
    self.assertEqual(set(["ru-gpu2"]), reference_values)

  def testIgnoresExternalIdentifierWithoutValueElement(self):
    root_string = self.root_string.format(
        "", "", """
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>jurisdiction-id</OtherType>
          </ExternalIdentifier>""")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()
    self.assertEqual(set(["ru-gpu2"]), reference_values)

  def testItRemovesDuplicatesIfMulitpleOfficesHaveSameJurisdiction(self):
    root_string = self.root_string.format(
        "", """
          <Office objectId="off0">
            <AdditionalData type="jurisdiction-id">ru-gpu2</AdditionalData>
          </Office>""", "")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_reference_values()
    self.assertEqual(set(["ru-gpu2"]), reference_values)

  # _gather_defined_values test
  def testReturnsASetOfGpUnitsFromGivenTree(self):
    root_string = self.root_string.format(
        """
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu1"/>""", "", "")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    validator = rules.ValidJurisdictionID(election_tree, None)
    reference_values = validator._gather_defined_values()
    self.assertEqual(set(["ru-gpu1", "ru-gpu2", "ru-gpu3"]), reference_values)

  # check tests
  def testEveryJurisdictionIdReferencesAValidGpUnit(self):
    root_string = self.root_string.format(
        """
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu1"/>""", """
          <Office objectId="off0">
            <AdditionalData type="jurisdiction-id">ru-gpu1</AdditionalData>
          </Office>""", """
          <ExternalIdentifier>
            <Type>other</Type>
            <OtherType>jurisdiction-id</OtherType>
            <Value>ru-gpu3</Value>
          </ExternalIdentifier>""")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    rules.ValidJurisdictionID(election_tree, None).check()

  def testRaisesAnElectionErrorIfJurisdictionIdIsNotAGpUnitId(self):
    root_string = self.root_string.format(
        """
          <GpUnit xsi:type="ReportingUnit" objectId="ru-gpu1"/>""", """
          <Office objectId="off0">
            <AdditionalData type="jurisdiction-id">ru-gpu99</AdditionalData>
          </Office>""", "")

    election_tree = etree.ElementTree(etree.fromstring(root_string))
    with self.assertRaises(base.ElectionError) as ee:
      rules.ValidJurisdictionID(election_tree, None).check()
    self.assertIn("ru-gpu99", str(ee.exception))


class GpUnitsHaveSingleRootTest(absltest.TestCase):

  def setUp(self):
    super(GpUnitsHaveSingleRootTest, self).setUp()
    self.gpunits_tree_validator = rules.GpUnitsHaveSingleRoot(None, None)

  def testSingleRoot(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru0002">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
          <ComposingGpUnitIds>ru0002</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    self.gpunits_tree_validator.election_tree = etree.ElementTree(
        etree.fromstring(root_string))
    self.gpunits_tree_validator.check()

  def testMultipleRootTreeFails(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru0002">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    with self.assertRaises(base.ElectionError) as cm:
      self.gpunits_tree_validator.election_tree = etree.ElementTree(
          etree.fromstring(root_string))
      self.gpunits_tree_validator.check()
    self.assertIn("GpUnits tree has more than one root", str(cm.exception))

  def testNoRootsTreeFails(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru0002">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
          <ComposingGpUnitIds>ru0002</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
          <ComposingGpUnitIds>ru_pre92426</ComposingGpUnitIds>
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    with self.assertRaises(base.ElectionError) as cm:
      self.gpunits_tree_validator.election_tree = etree.ElementTree(
          etree.fromstring(root_string))
      self.gpunits_tree_validator.check()
    self.assertIn("GpUnits have no geo district root.", str(cm.exception))


class GpUnitsCyclesRefsValidationTest(absltest.TestCase):

  def setUp(self):
    super(GpUnitsCyclesRefsValidationTest, self).setUp()
    self.gpunits_tree_validator = rules.GpUnitsCyclesRefsValidation(None, None)

  def testValidationFailsIfCyclesFormed(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru0002">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
          <ComposingGpUnitIds>ru_temp_id</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
          <ComposingGpUnitIds>ru_pre92426</ComposingGpUnitIds>
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    with self.assertRaises(base.ElectionError) as cm:
      self.gpunits_tree_validator.election_tree = etree.ElementTree(
          etree.fromstring(root_string))
      self.gpunits_tree_validator.check()
    self.assertIn("Cycle detected at node", str(cm.exception))

  def testValidationForValidTree(self):
    root_string = """
    <xml>
      <GpUnitCollection>
        <GpUnit objectId="ru0002">
          <ComposingGpUnitIds>ru_temp_id ru_pre92426</ComposingGpUnitIds>
        </GpUnit>
        <GpUnit objectId="ru_pre92426">
        </GpUnit>
        <GpUnit objectId="ru_temp_id">
        </GpUnit>
      </GpUnitCollection>
    </xml>
    """
    self.gpunits_tree_validator.election_tree = etree.ElementTree(
        etree.fromstring(root_string))
    self.gpunits_tree_validator.check()


class ElectionStartDatesTest(absltest.TestCase):

  def setUp(self):
    super(ElectionStartDatesTest, self).setUp()
    self.date_validator = rules.ElectionStartDates(None, None)
    self.today = datetime.datetime.now().date()
    self.election_string = """
    <Election>
      <StartDate>{}</StartDate>
      <EndDate>{}</EndDate>
    </Election>
    """

  def testStartDatesAreNotFlaggedIfNotInThePast(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=1),
        self.today + datetime.timedelta(days=2))
    election = etree.fromstring(election_string)
    self.date_validator.check(election)

  def testAWarningIsThrownIfStartDateIsInPast(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=-1),
        self.today + datetime.timedelta(days=2))
    election = etree.fromstring(election_string)
    with self.assertRaises(base.ElectionWarning):
      self.date_validator.check(election)


class ElectionEndDatesTest(absltest.TestCase):

  def setUp(self):
    super(ElectionEndDatesTest, self).setUp()
    self.date_validator = rules.ElectionEndDates(None, None)
    self.today = datetime.datetime.now().date()
    self.election_string = """
    <Election>
      <StartDate>{}</StartDate>
      <EndDate>{}</EndDate>
    </Election>
    """

  def testEndDatesAreNotFlaggedIfNotInThePast(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=1),
        self.today + datetime.timedelta(days=2))
    election = etree.fromstring(election_string)
    self.date_validator.check(election)

  def testAnErrorIsThrownIfEndDateIsInPast(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=1),
        self.today + datetime.timedelta(days=-2))
    election = etree.fromstring(election_string)
    with self.assertRaises(base.ElectionError):
      self.date_validator.check(election)

  def testAnErrorIsThrownIfEndDateIsBeforeStartDate(self):
    election_string = self.election_string.format(
        self.today + datetime.timedelta(days=2),
        self.today + datetime.timedelta(days=1))
    election = etree.fromstring(election_string)
    with self.assertRaises(base.ElectionError):
      self.date_validator.check(election)


class RulesTest(absltest.TestCase):

  def testAllRulesIncluded(self):
    all_rules = rules.ALL_RULES
    possible_rules = self._subclasses(base.BaseRule)
    possible_rules.remove(base.TreeRule)
    possible_rules.remove(base.ValidReferenceRule)
    possible_rules.remove(rules.ValidatePartyCollection)
    possible_rules.remove(base.DateRule)
    self.assertSetEqual(all_rules, possible_rules)

  def _subclasses(self, cls):
    children = cls.__subclasses__()
    subclasses = set(children)
    for c in children:
      subclasses.update(self._subclasses(c))
    return subclasses


if __name__ == "__main__":
  absltest.main()
