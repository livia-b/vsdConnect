#subset of features from  https://github.com/SICASFoundation/vsdConnect


import requests
try:
    from urllib.parse import urlparse
    from urllib.parse import quote as urlparse_quote
except:
    from urlparse import urlparse
    from urllib import quote as urlparse_quote
from pprint import pprint
import logging
import sys
import csv
import os
import tempfile
from six import string_types

from vsdConnect.models import APIBasic, APIPagination, APIFile, APIObject, APIObjectLink, APIFolder, \
    FolderPagination, ObjectPagination


################################################
#Connector
################################################



logger = logging.getLogger()
requests.packages.urllib3.disable_warnings()



class basicVSDConnect(object):

    def __init__(self, demo=True, user='', pw='', maxAttempts = 5):
        self.session = requests.Session()
        self.session.verify = False
        if demo:
            user = "demo@virtualskeleton.ch"
            pw = "demo"
            self.baseUrl = "https://demo.virtualskeleton.ch/api/"
        else:
            self.baseUrl = "https://virtualskeleton.ch/api/"
        self.session.auth = user, pw
        self.maxAttempts = maxAttempts
        self.maxAttempts401 = 2
        test = self._get(self.baseUrl + 'object_rights')
        self._get(self.baseUrl + '/objects', params = dict( rpp=10))
        if not test:
            raise RuntimeError

    #################################################
    #requests library wrappers
    ################################################

    def _download(self, url, filename):
        r = urlparse.urlparse(url)
        res = self.session.get(r.geturl(),params= r.params, stream = True)
        with open(filename, 'wb') as f:
            for chunk in res.iter_content(1024):
                f.write(chunk)

    def fullUrl(self, resource):
        """
        check if resource is selfUrl or relative path. a correct full path will be returned

        :param str resource: the api resource path
        :return: the full resource path
        :rtype: str
        """
        res = urlparse(str(resource))

        if res.scheme == 'https':
            return resource
        else:
            return self.url + resource

    def parseResource(self, resource, validate = True):
        """
        automatically use correct model and download data from server if necessary (typically if id is missing)
        :param resource: can be a jsonmodel, a dict, a full or partial url
        :param validate:
        :return: jsonmodel
        """

        #parse resource into selfUrl and dict(or json model)
        if isinstance(resource, APIBasic):
            selfUrl = resource.selfUrl
            if not validate:
                return resource
        else:
            if isinstance(resource, string_types ):
                selfUrl = self.fullUrl(resource)
                resource = {'selfUrl' : selfUrl}
            else:
                selfUrl = resource['selfUrl']

        #find correct model type
        oType, oId = selfUrl.split(self.baseUrl)[-1].split('/')
        resourceTypes = {
            'files': APIFile,
            'folders': APIFolder,
            'objects': APIObject,
            'object-links' : APIObjectLink
        }
        try:
            int(oId)
            modelType = resourceTypes[oType]
        except: #special case like objects/published
            if oType == 'objects':
                modelType = ObjectPagination
            elif oType == 'folders':
                modelType = FolderPagination

        #cast into json model
        model = modelType(**resource)

        if validate :
            try:
                model.validate()
            except Exception as e:
                #validation didn't pass (missing id) because I still need to download the object
                logging.info("Download %s into %s" %(resource['selfUrl'], modelType))
                objJson = self._get(resource['selfUrl'])
                pprint(objJson)
                model  = modelType(**objJson)
                model.validate()
        return model

    def _requestsAttempts(self, method, url, *args, **kwargs):
        """
        generic wrapper around request library with multiple attempts
        :param method: string of the method to call "get", "put"
        :param url: full  url
        :param args: args for request call
        :param kwargs: kwargs for request call
        :return: request json (raise if error after self.maxAttempts)
        """
        for i in range(self.maxAttempts):
            res = getattr(self.session, method)(url, *args, **kwargs)
            try:
                res.raise_for_status()
                return res.json()
            except:
                logger.info("Connection attempt %s/%s: %s" %(i, self.maxAttempts, res))
                if res.status_code == 401 and i > self.maxAttempts401:
                        raise
        #re-raise if > max attempts
        res.raise_for_status()
        return res.json()

    def _get(self, resource, *args, **kwargs): #reimplements VSDConnect.getRequest
        return self._requestsAttempts("get", resource, *args, **kwargs)

    def _put(self, resource, *args, **kwargs):#reimplements VSDConnect.putRequest
        return self._requestsAttempts("put", resource, *args, **kwargs)

    def _delete(self, resource, *args, **kwargs):#reimplements VSDConnect.postRequest
        return self._requestsAttempts("delete", resource, *args, **kwargs)

    def _post(self, resource, **kwargs):
        #not idempotent, no multiple  attempts
        res = self.session.post(self.fullUrl(resource), **kwargs)
        res.raise_for_status()
        return res.json()

    def optionObjects(self):
        res = self.session.options('/'.join([self.baseUrl,'objects']))
        res.raise_for_status()
        return res.json()


############################################################
# Pagination utilities
###########################################################

    def getAllItemsFromPage(self, objectJson):
        if objectJson is None:
            return []
        items = objectJson['items']
        tot = objectJson['totalCount']
        nextPageUrl = objectJson['nextPageUrl']
        while nextPageUrl:
            objectJson = self._get(nextPageUrl)
            items.extend(objectJson['items'])
            nextPageUrl = objectJson['nextPageUrl']
        assert (len(items) == tot)
        return items

    def iterateAllPaginated(self, objectJson):
        for item in objectJson['items']:
            yield item
        if objectJson['nextPageUrl']:
            for x in self.iterateAllPaginated(self._get(objectJson['nextPageUrl'])):
                yield x

##############################################################
# Folders
##############################################################

    def getFolder(self, id):
        return self.parseResource('folders/%s' %id, validate=True)

    def getFolders(self, idList=None):
        if idList is None:
            return self.getAllItemsFromPage(self._get(self.baseUrl + 'folders/'))
        items = []
        for curId in idList:
            items.append(self.getFolder(curId))
        return items

    def walkFolder(self, folderUrl, topdown=True):
        #similar to os.walk
        folderObject = self.parseResource(folderUrl)
        dirs = folderObject.childFolders
        nondirs = folderObject.containedObjects
        if dirs is None:
            dirs = []
        if nondirs is None:
            nondirs =[]
        if topdown:
            yield folderObject, dirs, nondirs

        for nextDir in dirs:
            for x in self.walkFolder(nextDir.selfUrl):
                yield x
        if not topdown:
                yield folderObject, dirs, nondirs

    def deleteFolderContent(self, folderObject):
        folderObject.containedObjects = None
        self._put(self.baseUrl + 'folders/', json=folderObject.to_struct())

    def addObjectsToFolder(self, folder, objIdList):
        target = self.getFolder(folder)
        if target.objects is None:
            target.objects = []
        for objId in objIdList:
            target.objects.append(selfUrl =  self.fullUrl(objId))
        return self._put('folders', data = target)

    def postFolder(self, parent, name, check = True):
        exists = False
        if check:
            siblings = self.getFolder(parent).get('childFolders', [])
            for sf in siblings:
                sfJson = self.getFolder(sf)
                if sfJson.get('name') == name:
                    exists = True
                    break

        if not exists:
            folderData = {'name' : name,
                          'parentFolder': {'selfUrl': self.fullUrl(parent)}}
            self._post(self.baseUrl + 'folders/', data=folderData)




#############################################################
# Objects
############################################################

    def getObjects(self, idList=None):
        if idList is None:
            idList = ''
        if idList in ['', 'published', 'unpublished']:
            return self.getAllItemsFromPage(self._get(self.baseUrl + 'objects/%s' % idList))

        items = []
        for curId in idList:
            items.append(self.getObject(curId))
        return items

    def getObject(self, id):
        return self.parseResource('objects/%s' % id, validate=True)

    def download(self, obj, folder = '.'):
        return self._download(obj['downloadUrl'],
                              os.path.join(folder, obj['name'] + '.zip' ))




if __name__ == '__main__':


    logging.basicConfig(level='INFO')
    folderId = 11 #demo
    from pprint import pprint

    api = basicVSDConnect(demo=True)
    publishedObjects = api.getObjects('published')

    print("See 5 published objects")
    for i,obj in enumerate(publishedObjects[:5]):
         print(i, ')')
         pprint(obj)

    print("Info on folder id 11")
    folder = api.getFolder(folderId)
    pprint(folder)

    for folderObject, subdirs, objects in api.walkFolder(folder.selfUrl):
         print(folderObject.name,' level ', folderObject.level)




