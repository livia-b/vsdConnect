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
    selfUrl = fieldURL(required=True)

class APIPagination(models.Base):
    totalCount = fields.IntField(required=True)
    pagination = fields.EmbeddedField(ParamsPagination)
    items = fields.ListField(APIBasic)
    nextPageUrl = fieldURL()

    def firstUrlInPage(self):
        firstItem = self.items[0]
        return firstItem.selfUrl

class APIFile(APIBasic):
    id = fields.IntField(required=True)
    createdDate = fields.StringField()
    downloadUrl = fieldURL()
    originalFileName = fields.StringField()
    anonymizedFileHashCode = fields.StringField()
    size = fields.StringField()
    fileHashCode = fields.StringField()

class APIObject(APIBasic):
    id = fields.IntField(required=True)
    name = fields.StringField(required=True)
    type = fields.EmbeddedField(APIBasic)
    description  = fields.StringField()
    objectGroupRights = fields.ListField(APIBasic)
    objectUserRights = fields.StringField()
    objectPreviews = fields.StringField()
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
    id = fields.IntField(required=True)
    description = fields.StringField()
    object1 = fields.StringField()
    object2 = fields.StringField()

class APIFolder(APIBasic):
    id = fields.IntField(required=True)
    level = fields.StringField()
    parentFolder = fields.EmbeddedField(APIBasic)
    childFolders = fields.ListField('APIFolder')
    folderGroupRights = fields.StringField()
    folderUserRights = fields.StringField()
    containedObjects = fields.ListField(APIBasic)

class FolderPagination(APIPagination):
    items = fields.ListField(APIFolder)


