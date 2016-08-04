from jsonmodels import models, fields, errors, validators
import  logging
logger = logging.getLogger(__name__)

##########################################
# walk the model (from jsonmodels.parsers.to_struct()

def _iterateModel(model, validate=True, maxDepth=None, actionOnValue=None):
    """to_struct is equivalent to:
    _iterateModel(validate=True, maxElements = -1, maxDepth = None, actionOnValue = None

    """
    if not (maxDepth > 0 or maxDepth is None):
        return ".."

    nextKwargs = dict(
        validate=validate,
        maxDepth=None if maxDepth is None else maxDepth - 1,
        actionOnValue=actionOnValue,
    )

    if not isinstance(model, models.Base):
        return model

    if validate:
        model.validate()

    resp = {}
    for name, field in model:
        value = field.__get__(model)
        if value is None:
            continue
        if actionOnValue:
            value = actionOnValue(name,value)

        if isinstance(value, list):
            resp[name] = [_iterateModel(item, **nextKwargs) for item in value]
        else:
            resp[name] = _iterateModel(value, **nextKwargs)
    return resp





################################################
# JWT token
################################################
class APIToken(models.Base):
    tokenType = fields.StringField()
    tokenValue = fields.StringField()


################################################
# Models
################################################

class fieldURL(fields.StringField):
    pass  # add url-specific fields?


class longIntField(fields.IntField):
    types = (int, long,)


class ParamsPagination(models.Base):
    rpp = fields.IntField()
    page = fields.IntField()




class APIBasic(models.Base):
    selfUrl = fieldURL()

    def __str__(self):
        return '{name} {url}'.format(name=self.__class__.__name__, url=self.selfUrl)


class APIBaseId(APIBasic):
    id = fields.IntField()

    def __str__(self):
        return '{name} {url} {selfname}'.format(name=self.__class__.__name__, url=self.id,
                                                selfname=getattr(self, 'name', ""))

    def pprint(self,indent=2, maxDepth = 3, maxElements = 1, **kwargs):
        from json import dumps
        def func(name, value):
            if isinstance(value, list):
                if maxElements is None or len(value) < maxElements:
                    return maxElements
                else:
                    return value [:maxElements] + [ "other %s elements" %(len(value) - maxElements)]
            elif isinstance(value, dict):
                value.pop('pagination',None)
                value.pop('nextPageUrl', None)
                return value
            elif isinstance(value, APIPagination):
                pass
            else:
                return value
        kwargs['indent'] = indent
        res = _iterateModel(self, validate=False, maxDepth=maxDepth, actionOnValue=func)
        return dumps(res, **kwargs)


class APIPagination(models.Base):
    totalCount = fields.IntField(required=True)
    pagination = fields.EmbeddedField(ParamsPagination, required=True)
    items = fields.ListField(dict)  # generic dict in order to retain all the keys
    nextPageUrl = fieldURL()


    def pprint(self,  indent=2, **kwargs):
        from json import dumps
        kwargs['indent'] = indent
        maxElements = 3
        itemList = [self.items[:maxElements]] + []*(self.totalCount-maxElements)
        copy = self.__class__(items=itemList )
        res = iteratePretty()(copy)
        return dumps(res, **kwargs)

    def firstUrlInPage(self):
        firstItem = self.items[0]
        return firstItem.selfUrl

class APIBasePagination(APIPagination):
    items = fields.ListField(APIBasic)


class APIFileUploadResponse(APIBasic):
    relatedObject = fields.EmbeddedField(APIBasic)
    file = fields.EmbeddedField(APIBasic)


class APIFile(APIBaseId):
    createdDate = fields.StringField()
    downloadUrl = fieldURL()
    originalFileName = fields.StringField()
    anonymizedFileHashCode = fields.StringField()
    size = longIntField()
    fileHashCode = fields.StringField()
    objects = fields.EmbeddedField(APIPagination)  # ObjectPagination


class FilePagination(APIPagination):
    items = fields.ListField(APIFile)


class APIPreview(APIBaseId):
    imageUrl = fieldURL()
    thumbnailUrl = fieldURL()


class APIObjectType(APIBasic):
    displayName = fields.StringField()
    name = fields.StringField()
    displayNameShort = fields.StringField()


class APIObjectUserRight(APIBasic):
    pass


class APIObjectGroupRight(APIBasic):
    pass


class APILicense(APIBasic):
    pass


class APIObjectRight(APIBasic):
    pass


class APIGroup(APIBasic):
    pass


class APIUser(APIBasic):
    pass


class APIObject(APIBaseId):
    name = fields.StringField()
    type = fields.EmbeddedField(APIObjectType)
    description = fields.StringField()
    objectGroupRights = fields.ListField(APIObjectGroupRight)
    objectUserRights = fields.ListField(APIObjectUserRight)
    objectPreviews = fields.ListField(APIPreview)
    createdDate = fields.StringField()
    modality = fields.StringField()
    ontologyItems = fields.EmbeddedField(APIPagination)
    ontologyItemRelations = fields.EmbeddedField(APIPagination)
    ontologyCount = fields.IntField()
    license = fields.EmbeddedField(APILicense)
    files = fields.EmbeddedField(APIPagination)
    linkedObjects = fields.EmbeddedField(APIPagination)
    linkedObjectRelations = fields.EmbeddedField(APIPagination)
    downloadUrl = fieldURL()


class ObjectPagination(APIPagination):
    items = fields.ListField(APIObject)


class APIObjectLink(APIBaseId):
    description = fields.StringField()
    object1 = fields.EmbeddedField(APIBasic)
    object2 = fields.EmbeddedField(APIBasic)


class APIFolder(APIBaseId):
    name = fields.StringField()
    level = fields.IntField()
    parentFolder = fields.EmbeddedField(APIBasic)
    childFolders = fields.ListField(APIBasic)  # fields.ListField([ 'APIFolder'])
    folderGroupRights = fields.ListField(APIBasic)
    folderUserRights = fields.ListField(APIBasic)
    containedObjects = fields.ListField(APIBasic)


class FolderPagination(APIPagination):
    items = fields.ListField(APIFolder)


class APIObjectOntology(APIBasic):
    pass


class APIModality(APIBasic):
    pass


class APIOntology(APIBasic):
    pass


###############################
# API url dictionary
############################
resourceTypes = {
    'files': APIFile,
    'folders': APIFolder,
    'objects': APIObject,
    'object-links': APIObjectLink
}


##########################################
# Object types
##########################################
class ImageModality(APIBaseId):
    description = fields.StringField()
    name = fields.StringField()


class RawImageData(models.Base):
    sliceThickness = fields.FloatField()
    kilovoltPeak = fields.FloatField()
    spaceBetweenSlices = fields.FloatField()
    modality = fields.EmbeddedField(ImageModality)


class RawImage(APIObject):
    rawImage = fields.EmbeddedField(RawImageData)


class SurfaceModel(APIObject):
    pass


class Subject(APIObject):
    pass


class SegmentationImageData(models.Base):
    methodDescription = fields.StringField()
    segmentationMethod = fields.EmbeddedField(
        dict)  # {u'displayName': u'Manual', u'id': 3, u'selfUrl': u'https://www.virtualskeleton.ch/api/segmentation_methods/3', u'name': u'Manual'})


class SegmentationImage(APIObject):
    segmentationImage = fields.EmbeddedField(SegmentationImageData)


class ClinicalStudyDefinition(APIObject):
    pass


class ClinicalStudyData(APIObject):
    pass


class StatisticalModel(APIObject):
    pass

# ##
# ## View Models
# ##
#

#
# class APIRawImage(object):
#     """
#     API class for Raw Image view model
#
#
#     :attributes:
#         * sliceThickness
#         * spaceBetweenSlices
#         * kilovoltPeak
#         * modality
#
#     """
#     oKeys = list([
#         'sliceThickness',
#         'spaceBetweenSlices',
#         'kilovoltPeak',
#         'modality'
#         ])
#
#
# class APISegImage(object):
#     """
#     API class for segmenation image view model
#
#
#     :attributes:
#         * methodDescription
#         * segmentationMethod
#
#     """
#     oKeys = list([
#         'methodDescription',
#         'segmentationMethod'
#         ])
#
# # #class APIStatisticalModel(object):
#     """
#     API class for Statistical model view model - empty
#     """
#
# ## class APIStudyModel(object):
#     """
#     API class for Statistical model view model - empty
#     """
#
#
#
# class APISubject(object):
#     """
#     API class for Subject view model
#
#     :attributes:
#         * subjectKey
#
#     """
#     oKeys = list([
#         'subjectKey'
#         ])
#
#
# ## class APICtData(object):
#     """
#     API class for clinical trial data view model  - empty
#     """
#
# class APICtDef(object):
#     """
#     API class for clinical trail definition view model
#
#     :attributes:
#     * studyOID
#     * studyName
#     * studyDescription
#     * protocolName
#     * metaDataVersionOID
#     * metaDataVersionName
#
#     """
#
#     oKeys = list([
#         'studyOID',
#         'studyName',
#         'studyDescription',
#         'protocolName',
#         'metaDataVersionOID',
#         'metaDataVersionName'
#         ])
#
# class APIGenPlatform(object):
#     """
#     API class for  genomic platform view model
#     """
#
# class APIGenSeries(object):
#     """
#     API class for genomic series view model
#     """
#
# class APIGenSample(object):
#     """
#     API class for genomic sample view model
#     """
#
# class APIPlain(object):
#     """
#     API class for plain (undefined object) model view model
#     """
#
# class APIPlainSubject(object):
#     """
#     API class for plain subject (undefined subject object) model view model
#     """
