#!/usr/bin/python
"""
=======
INFOS
=======
* python version: 3.5
* connectVSD 0.8.1
* module: models
* @author: Michael Kistler 2016, Livia B.

========
CHANGES
========
* implemented objects as jsonmodels

"""

from jsonmodels import models, fields, errors, validators
if PYTHON3:
    from pathlib import Path, PurePath, WindowsPath


################################################
#Custom validators
################################################

class ListValidator(object):

    """Validator for a list."""

    def __init__(self, itemlist):
        """Init.

        :param items: list of items to check against.
        :param bool exclusive: If `True`, then validated value must be strongly
            bigger than given threshold.

        """
        self.itemlist = itemlist

    def validate(self, value):
        """Validate value."""
       
        if value not in self.itemlist:
            raise errors.ValidationError(
                "'{value}' is not accepted, acceptable values are: ('{itemlist}').".format(
                    value=value, itemlist=self.itemlist))


    def modify_schema(self, field_schema):
        """Modify field schema."""
        field_schema['itemlist'] = self.itemlist



################################################
#Models parameters
################################################

class URLField(fields.StringField):
    pass #add url-specific fields?



##########################################
# Attributes Data
##########################################

class PaginationParameter(models.Base):
    """
    pagination parameters

    """
    
    rpp = fields.IntField(
        required=True,
        validators=ListValidator([10, 25, 50, 100, 250, 500])
        )

    page = fields.IntField(
        required=True,
        validators=validators.Min(0)
        )


################################################
#View Models
################################################

class APIVersion(models.Base):
    """
    the api version view model
    """
    major = fields.IntField()
    minor = fields.IntField()
    build = fields.IntField()
    revision = fields.IntField()
    majorRevision = fields.IntField()
    minorRevision = fields.IntField()

class HttpContent(models.Base):
    """
    header content
    """
    headers = fields.StringField()

class HttpMethod(models.Base):
    """
    http request method
    """
    method = fields.IntField()

class HttpRequestMessage(models.Base):
    """
    Http request view model
    """
    version = fields.EmbeddedField(APIVersion)
    content = fields.EmbeddedField(HttpContent) 
    method = fields.EmbeddedField(HttpMethod)
    requestUri = URLField()
    headers = fields.StringField()
    proertiews = fields.EmbeddedField(dict)

class HttpResponseMessage(models.Base):
    """
    http response message view model
    """
    version = fields.EmbeddedField(APIVersion)
    content = fields.EmbeddedField(HttpContent) 
    statusCode = fields.IntField()
    reasonPhrase = fields.StringField()
    headers = fields.StringField()
    requestMessage = fields.EmbeddedField(HttpRequestMessage)
    isSuccessStatusCode = fields.BoolField()

class  Token(models.Base):
    """
    API class to work with the tokens
    Supported token: JWT
    """

    tokenType = fields.StringField()
    tokenValue = fields.StringField()


class APIBase(models.Base):
    """
    Basic for all classes with selfUrl

    """

    selfUrl = fields.StringField()

    def __str__(self):
        return '{name} {url}'.format(name=self.__class__.__name__, url = self.selfUrl)



    def get(self):
        """
        get the object as json readable structure (dict)

        :return: json 
        :rtype: json
        """
        return json.dumps(self.to_struct())


    def set(self, data):
        """
        set the object content 

        :param json data: the data for the object in json format
        :return: json 
        :rtype: json

        """
        # takes existing fields and sets its value from the input data
        for name, field in self.iterate_over_fields():
            print('name: {0} - value: {1} - type: {2}'. format(name, data[name], type(field)))
            field.__set__(self, data[name])

  
    def show(self):
        """
        show the object as json readable structure (dict), nicely formated

        """
        print(json.dumps(self.to_struct(), sort_keys = True, indent = 4))


    
    def save(self, fp = 'object.json'):
        """
        save the object as json to the given filepath

        :params Path fp: the filepath to the file
        :return: the path to the stored file
        :rtype: Path

        """

        fp = Path(fp)

        if fp.is_file():
            fp.unlink()
            fp.touch()
        else:
            fp.touch()
            

        with fp.open('w') as outfile:
            json.dump(self.to_struct(), outfile, indent = 4)
            
        return fp


class APIBaseID(APIBase):
    """
    id and selfUrl
    """
    id = fields.IntField()

    def __str__(self):
        return '{name} {url} {selfname}'.format(name=self.__class__.__name__, url = self.id, selfname = getattr(self, 'name', ""))

class APIBaseExt(APIBaseID):
    """
    id, name, display name and selfUrl
    """
    name = fields.StringField()
    displayName = fields.StringField()


class APIBaseN3(APIBase):
    """
    for semantic triple storage
    """
    subject = fields.EmbeddedField(APIBaseExt) # will be most likely a APIBaseExt
    predicate = fields.EmbeddedField(APIBaseExt) # will be most likely a APIBaseExt
    object = fields.EmbeddedField(APIBaseExt) # will be most likely a APIBaseExt


class Preview(APIBaseID):
    imageUrl = URLField()
    thumbnailUrl = URLField()



class ObjectOntology(APIBase):
    pass

class Ontology(APIBase):
    pass




class Pagination(models.Base):
    """
    API class for Pagination results
    """

    totalCount = fields.IntField(required=True)
    pagination = fields.EmbeddedField(PaginationParameter, required=True)
    items = fields.ListField(dict) #generic dict in order to retain all the keys
    nextPageUrl = URLField()

    def firstUrlInPage(self):
        """
        get the selfurl of the first item in the paginated list
        
        :return: selfUrl
        :rtype: string

        """
        firstItem = self.items[0]
        return firstItem.selfUrl




################################################
#FILES
################################################

class File(APIBaseID):
    createdDate = fields.StringField()
    downloadUrl = URLField()
    originalFileName = fields.StringField()
    anonymizedFileHashCode = fields.StringField()
    size = fields.IntField()
    fileHashCode = fields.StringField()
    objects = fields.EmbeddedField(Pagination) #ObjectPagination



################################################
#FOLDER
################################################
class Folder(APIBaseID):
    name = fields.StringField()
    level = fields.IntField()
    parentFolder = fields.EmbeddedField(APIBase)
    childFolders = fields.ListField(APIBase)#fields.ListField([ 'Folder'])
    folderGroupRights = fields.ListField(APIBase)
    folderUserRights = fields.ListField(APIBase)
    containedObjects = fields.ListField(APIBase)

class FolderPagination(Pagination):
    """
    API class for Pagination results containing folders
    """
    items = fields.ListField(Folder)



################################################
#FOLDER RIGHTS
################################################

class FolderRight(APIBaseID):
    """
    represents a folder right
    """
    name = fields.StringField()
    rightValue = fields.IntField()


class FolderRightPagination(Pagination):
    """
    API class for pagination result containing folder rights
    """
    items = fields.ListField(FolderRight)

class FolderRightSet(APIBaseID):
    """
    folder rights set 
    """
    name = fields.StringField()
    folderRights = fields.ListField(APIBase)


class FolderRightSetPagination(Pagination):
    """
    API class for pagination result containing folder rights
    """
    items = fields.ListField(FolderRightSet)

class FolderGroupRight(APIBaseID):
    """
    relations between folder, group and right (permission)
    """
    relatedFolder = fields.EmbeddedField(APIBase)
    relatedGroup = fields.EmbeddedField(APIBase)
    relatedRights= fields.ListField(APIBase)


class FolderUserRight(APIBaseID):
    """
    relations between folder, user and right (permission)
    """
    relatedFolder = fields.EmbeddedField(APIBase)
    relatedUser = fields.EmbeddedField(APIBase)
    relatedRights= fields.ListField(APIBase)

class FolderGroupRightPagination(Pagination):
    """
    API class for pagination result containing folder group rights
    """
    items = fields.ListField(FolderGroupRight)

class FolderUserRightPagination(Pagination):
    """
    API class for pagination result containing folder userrights
    """
    items = fields.ListField(FolderUserRight)






################################################
#GROUP
################################################

class Group(APIBaseID):
    """
    class for groups 
    """
    name = fields.StringField()
    chief = fields.EmbeddedField(APIBase)

class GroupPagination(Pagination):
    """
    class for pagination results containing groups
    """

    items = fields.ListField(Group)





################################################
#LICENSES
################################################

class License(APIBase):
    """
    class for licenses
    """
    name = fields.StringField()
    description = fields.StringField()

class LicensePagination(Pagination):
    """
    class for pagination results containing groups
    """

    items = fields.ListField(License)




################################################
#MODALITY
################################################

class Modality(APIBaseID):
    description = fields.StringField()
    name = fields.StringField()

class ModalityPagination(Pagination):
    """
    class for pagination results containing modalities
    """

    items = fields.ListField(Modality)



################################################
#OBJECTS LINKS
################################################
class ObjectLinks(APIBaseID):
    """
    a link betwen two objects
    """
    object1 = fields.EmbeddedField(APIBase)
    object2 = fields.EmbeddedField(APIBase)
    description = fields.StringField()



################################################
#OBJECTS ONTOLOGY & ONTOLOGY
################################################
class ObjectOntology(APIBaseID):
    """
    A relation between an object and an ontology item
    """
    position = fields.IntField()
    type = fields.IntField()
    object = fields.EmbeddedField(APIBase)
    ontologyItem = fields.EmbeddedField(APIBase)



class OntologyItem(APIBaseID):
    """
    An ontology item
    """

    term = fields.StringField()
    type = fields.IntField()

class OntologyItemPagination(Pagination):
    """
    class for pagination results containing ontology items
    """

    items = fields.ListField(OntologyItem)

class OntologyOptions(models.Base):
    """
    additional information for the ontologies resource.
    """
    types = fields.ListField(dict)

################################################
#OBJECTS RIGHTS
################################################
class ObjectRight(APIBase):
    """
    Represents an object right.
    """
    name = fields.StringField()
    rightValue = fields.IntField()

class ObjectRightPagination(Pagination):
    """
    class for pagination results containing object rights
    """
    items = fields.ListField(ObjectRight)


class ObjectRightSet(APIBaseID):
    """
    object rights set 
    """
    name = fields.StringField()
    objectRights = fields.ListField(APIBase)


class ObjectRightSetPagination(Pagination):
    """
    API class for pagination result containing object rights
    """
    items = fields.ListField(ObjectRightSet)

class ObjectGroupRight(APIBaseID):
    """
    relations between object, group and right (permission)
    """
    relatedObject = fields.EmbeddedField(APIBase)
    relatedGroup = fields.EmbeddedField(APIBase)
    relatedRights= fields.ListField(APIBase)


class ObjectUserRight(APIBaseID):
    """
    relations between object, user and right (permission)
    """
    relatedObject = fields.EmbeddedField(APIBase)
    relatedUser = fields.EmbeddedField(APIBase)
    relatedRights= fields.ListField(APIBase)

class ObjectGroupRightPagination(Pagination):
    """
    API class for pagination result containing object group rights
    """
    items = fields.ListField(FolderGroupRight)

class ObjectUserRightPagination(Pagination):
    """
    API class for pagination result containing object userrights
    """
    items = fields.ListField(ObjectUserRight)



################################################
#OBJECTS
################################################

class ObjectType(APIBase):
    """
    for semantic triple storage
    """
    name = fields.StringField()
    displayName = fields.StringField()   
    displayNameShort = fields.StringField()


class APIObject(APIBaseID):
    """
    base object class
    """
    createdDate = fields.StringField()
    name = fields.StringField()
    description  = fields.StringField()
    ontologyCount = fields.IntField()
    type = fields.EmbeddedField(ObjectType)
    downloadUrl = URLField()
    license = fields.EmbeddedField(APIBase)
    files = fields.EmbeddedField(Pagination)
    linkedObjects = fields.EmbeddedField(Pagination)
    linkedObjectRelations = fields.EmbeddedField(Pagination)
    ontologyItems = fields.EmbeddedField(Pagination)
    ontologyItemRelations = fields.EmbeddedField(Pagination)
    objectPreviews = fields.ListField(Preview)
    objectGroupRights = fields.ListField(ObjectGroupRight)
    objectUserRights = fields.ListField(ObjectUserRight)



class ObjectPagination(Pagination):
    """
    API class for Pagination results containing objects
    """
    items = fields.ListField(APIObject)

################################################
#specification for Object types
################################################


class RawImageData(models.Base):
    """
    raw image attributes
    """
    sliceThickness = fields.FloatField()
    kilovoltPeak = fields.FloatField()
    spaceBetweenSlices = fields.FloatField()
    modality = fields.EmbeddedField(Modality)


class RawImageObject(APIObject):
    """
    API class for raw image view model
    """
    rawImage = fields.EmbeddedField(RawImageData)

class SegmentationImageData(models.Base):
    """
    segmentation specific attributes

    """
    methodDescription = fields.StringField()
    segmentationMethod = fields.EmbeddedField(APIBase) 
    #{u'displayName': u'Manual', u'id': 3, u'selfUrl': u'https://www.virtualskeleton.ch/api/segmentation_methods/3', u'name': u'Manual'})

class SegmentationImageObject(APIObject):
    """
    API class for segmenation image view model
    """
    segmentationImage = fields.EmbeddedField(SegmentationImageData)

class StatisticalModelObject(APIObject):
    """
    API class for Statistical model view model - empty
    """
    pass


class SurfaceModelData(APIObject):
    """
    attributes of surface model
    """
    vectorCount = fields.IntField()
    minX = fields.FloatField()
    minY = fields.FloatField()
    minZ = fields.FloatField()
    maxX = fields.FloatField()
    maxY = fields.FloatField()
    maxZ = fields.FloatField()

class SurfaceModelObject(APIObject):
    """
    API class for surface model view model
    """
    surfaceModel = fields.EmbeddedField(SurfaceModelData)


class SubjectData(APIObject):
    """
    attributes for subject data
    """
    subjectKey = fields.StringField()


class SubjectObject(APIObject):
    """
    API class for Subject view model

    """
    subject = fields.EmbeddedField(SubjectData)


class ClinicalStudyDataObject(APIObject):
    """
    API class for clinical trial data view model  - empty
    """
    subject = fields.EmbeddedField(SubjectData)
    clinicalStudyDefinition = fields.EmbeddedField(APIBase)

class ClincalStudyDefinitionData(models.Base):
    """
    attributes for clinical study definition
    """
    studyOID = fields.StringField()
    studyName = fields.StringField()
    studyDescription = fields.StringField()
    protocolName = fields.StringField()
    metaDataVersionOID = fields.StringField()
    metaDataVersionName = fields.StringField()

class ClinicalStudyDefinitionObject(APIObject):
    """
    API class for clinical trail definition view model
    """
    clincalStudyDefinition = fields.EmbeddedField(ClincalStudyDefinitionData)


class GenomicPlatformObject(APIObject):
    """
    API class for  genomic platform view model - empty
    """
    pass

class GenomicSeriesObject(APIObject):
    """
    API class for genomic series view model - empty
    """
    pass

class GenomicSampleObject(APIObject):
    """
    API class for genomic sample view model - empty
    """
    pass

class StudyObject(APIObject):
    """
    API class for study 
    """
    pass

class PlainObject(APIObject):
    """
    API class for plain (undefined object) model view model
    """
    pass

class PlainSubjectObject(APIObject):
    """
    API class for plain subject (undefined subject object) model view model
    """
    pass

class ObjectOptions(models.Base):
    """
    class for additional information of the API objects
    """

    genomicPlatform = fields.EmbeddedField(GenomicPlatformObject)
    genomicSample = fields.EmbeddedField(GenomicSampleObject)
    genomicSeries = fields.EmbeddedField(GenomicSeriesObject)
    rawImage = fields.EmbeddedField(RawImageObject)
    segmentationImage = fields.EmbeddedField(SegmentationImageObject)
    statisticalModel = fields.EmbeddedField(StatisticalModelObject)
    clinicalStudyData = fields.EmbeddedField(ClinicalStudyDataObject)
    clinicalStudyDefinition = fields.EmbeddedField(ClinicalStudyDefinitionObject)
    study = fields.EmbeddedField(StudyObject)
    subject = fields.EmbeddedField(StudyObject)
    surfaceModel = fields.EmbeddedField(SurfaceModelObject)


################################################
#SEGMENTATION METHOD
################################################


class SegmentationMethod(APIBaseID):
    """
    segmentation methods view model
    """
    name = fields.StringField()
    displayName = fields.StringField()



################################################
#SEARCH
################################################
class DynamicSearchLogicalOperator(models.Base):
    """
    logical operator view model
    """
    name = fields.StringField()
    displayName = fields.StringField()
    position = fields.IntField()

class DynamicSearchComparisonOperator(models.Base):
    """
    docstring 
    """

    name = fields.StringField()
    displayName = fields.StringField()
    position = fields.IntField()
    typeaheadUrl = fields.StringField()

class DynamicSearchSourceField(models.Base):
    """
    fiels view model for dynamic search
    """
    name = fields.StringField()
    displayName = fields.StringField()
    position = fields.IntField()
    comparisonOperators = fields.ListField(DynamicSearchComparisonOperator)

class DynamicSearchSourceType(models.Base):
    """
    source type view model for search
    """
    name = fields.StringField()
    displayName = fields.StringField()
    position = fields.IntField()
    sourceFields = fields.ListField(DynamicSearchSourceField)

class DynamicSearchOptions(models.Base):
    """ for DynamicSearchOptions"""
    
    logicalOperators = fields.ListField(DynamicSearchLogicalOperator)
    sourceTypes = fields.ListField(DynamicSearchSourceType)

class DynamicSearchInputItem(models.Base):
    """ docstring"""
    data = fields.EmbeddedField(APIObject)
    displayName = fields.StringField()
    isTypeahead = fields.BoolField()

class DynamicSearchCondition(models.Base):
    """docstring """
    sourceField = fields.EmbeddedField(DynamicSearchSourceField)
    comparisonOperator = fields.EmbeddedField(DynamicSearchComparisonOperator)
    inputItem = fields.EmbeddedField(DynamicSearchInputItem)



class DynamicSearchGroup(models.Base):
    """docstring"""

    sourceType = fields.EmbeddedField(DynamicSearchSourceType)
    logicalOperator = fields.EmbeddedField(DynamicSearchLogicalOperator)
    conditions = fields.ListField(DynamicSearchCondition)
    groups = fields.ListField(dict) # DynamicSearchGroup -> recursive...

################################################
#UPLOAD
################################################
class UploadResponse(models.Base):
    """
    a response consisting of a combination between a file and an object after the upload
    """
    file = fields.EmbeddedField(APIBase)
    relatedObject = fields.EmbeddedField(APIBase)




################################################
#USERS
################################################
class User(APIBaseID):
    """
    Users of the repository
    """
    username = fields.StringField()



###############################
# API url dictionary
############################
resourceTypes = {
    'files': File,
    'folders': Folder,
    'objects': APIObject,
    'object-links' : ObjectLink
}