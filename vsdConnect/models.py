from jsonmodels import models, fields, errors, validators
################################################
#Models
################################################

class fieldURL(fields.StringField):
    pass #add url-specific fields?

class ParamsPagination(models.Base):
    rpp = fields.IntField()
    page = fields.IntField()

class APIBasic(models.Base):
    selfUrl = fieldURL()

class APIPagination(models.Base):
    totalCount = fields.IntField()
    pagination = fields.EmbeddedField(ParamsPagination)
    items = fields.ListField(dict) #generic dict in order to retain all the keys
    nextPageUrl = fieldURL()

    def firstUrlInPage(self):
        firstItem = self.items[0]
        return firstItem.selfUrl

class APIFile(APIBasic):
    id = fields.IntField()
    createdDate = fields.StringField()
    downloadUrl = fieldURL()
    originalFileName = fields.StringField()
    anonymizedFileHashCode = fields.StringField()
    size = fields.IntField()
    fileHashCode = fields.StringField()
    objects = fields.EmbeddedField(APIPagination) #ObjectPagination

class FilePagination(APIPagination):
    items = fields.ListField(APIFile)

class APIPreview(APIBasic):
    imageUrl = fieldURL()
    thumbnailUrl = fieldURL()
    id = fields.IntField()

class APIObjectType(APIBasic):
    displayName = fields.StringField()
    name = fields.StringField()
    displayNameShort = fields.StringField()

class APIObject(APIBasic):
    id = fields.IntField()
    name = fields.StringField()
    type = fields.EmbeddedField(APIObjectType)
    description  = fields.StringField()
    objectGroupRights = fields.ListField(APIBasic)
    objectUserRights = fields.StringField()
    objectPreviews = fields.ListField(APIPreview)
    createdDate = fields.StringField()
    modality = fields.StringField()
    ontologyItems = fields.EmbeddedField(APIPagination)
    ontologyItemRelations = fields.EmbeddedField(APIPagination)
    ontologyCount = fields.IntField()
    license = fields.StringField()
    files = fields.EmbeddedField(APIPagination)
    linkedObjects = fields.EmbeddedField('ObjectPagination')
    linkedObjectRelations = fields.EmbeddedField(APIPagination)
    downloadUrl = fieldURL()

class ObjectPagination(APIPagination):
    items = fields.ListField(APIObject)

class APIObjectLink(APIBasic):
    id = fields.IntField()
    description = fields.StringField()
    object1 = fields.StringField()
    object2 = fields.StringField()

class APIFolder(APIBasic):
    id = fields.IntField()
    name = fields.StringField()
    level = fields.IntField()
    parentFolder = fields.EmbeddedField(APIBasic)
    childFolders = fields.ListField([ 'APIFolder'])
    folderGroupRights = fields.StringField()
    folderUserRights = fields.StringField()
    containedObjects = fields.ListField(APIBasic)

class FolderPagination(APIPagination):
    items = fields.ListField(APIFolder)


class RawImage(APIObject):
    rawImage = fields.EmbeddedField(dict) #{u'sliceThickness': None, u'kilovoltPeak': None, u'spaceBetweenSlices': None, u'modality': {u'description': u'White Matter Probabilistic Map', u'id': 39, u'selfUrl': u'https://demo.virtualskeleton.ch/api/modalities/39', u'name': u'MR_WM_prob'}}

class RawImage(APIObject):
    rawImage = fields.EmbeddedField(dict)

class SurfaceModel(APIObject):
    pass

class Subject(APIObject):
    pass

class SegmentationImage(APIObject):
    pass

class ClinicalStudyDefinition(APIObject):
    pass

class ClinicalStudyData(APIObject):
    pass

class StatisticalModel(APIObject):
    pass