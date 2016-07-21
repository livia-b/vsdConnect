#!/usr/bin/python
"""
=======
INFOS
=======
* connectVSD 0.8.1
* python version: 3
* @author: Michael Kistler 2015

========
CHANGES
========
* changed / added JwT auth
* object-types added

"""

from __future__ import print_function

import math
import hashlib

from datetime import datetime
from calendar import timegm
import base64

import urllib
import jwt

try: #if PYTHON3:
    from urllib.parse import urlparse
    from urllib.parse import quote as urlparse_quote
except ImportError:
    from urlparse import urlparse
    from urllib import quote as urlparse_quote

import json

from pathlib import Path, PurePath, WindowsPath
import requests
from requests.auth import AuthBase

import io
import base64
import zlib

try:
    import lxml.etree as ET
except:
    import xml.etree.ElementTree as ET

import models as vsdModels
import logging

logger = logging.getLogger(__name__)

requests.packages.urllib3.disable_warnings()


class SAMLAuth(AuthBase):
    """Attaches SMAL to the given Request object. extends the request package auth class"""

    def __init__(self, enctoken):
        self.enctoken = enctoken

    def __call__(self, r):
        # modify and return the request
        r.headers['Authorization'] = b'SAML auth=' + self.enctoken
        return r


def samltoken(fp, stsurl='https://ciam-dev-chic.custodix.com/sts/services/STS'):
    """
    generates the saml auth token from a credentials file

    :param Path fp: file with the credentials (xml file)
    :param str stsurl: url to the STS authority
    :return: enctoken - the encoded token
    :rtype: byte
    """

    if fp.is_file():
        tree = ET.ElementTree()
        dom = tree.parse(str(fp))
        authdata = ET.tostring(dom, encoding='utf-8')

    # send the xml in the attachment to https://ciam-dev-chic.custodix.com/sts/services/STS
    r = requests.post(stsurl, data=authdata, verify=False)

    if r.status_code == 200:

        fileobject = io.BytesIO(r.content)

        tree = ET.ElementTree()
        dom = tree.parse(fileobject)
        saml = ET.tostring(dom, method="xml", encoding="utf-8")

        # ZLIB (RFC 1950) compress the retrieved SAML token.
        ztoken = zlib.compress(saml, 9)

        # Base64 (RFC 4648) encode the compressed SAML token.
        enctoken = base64.b64encode(ztoken)
        return enctoken
    else:
        return None


class JWTAuth(AuthBase):
    """Attaches JMT to the given Request object. extends the request package auth class"""

    def __init__(self, enctoken):
        self.enctoken = enctoken

    def __call__(self, r):
        # modify and return the request
        r.headers['Authorization'] = 'Bearer ' + self.enctoken
        return r


class VSDConnecter:
    def __init__(
            self,
            authtype='jwt',
            url="https://demo.virtualskeleton.ch/api/",
            username="demo@virtualskeleton.ch",
            password="demo",
            version="",
            token=None,
    ):

        self.version = version
        self.url = url + version
        self.s = requests.Session()
        self.s.verify = False
        self.authtype = authtype
        self.maxAttempts = 3
        self.maxAttempts401 = 2

        if version:
            self.version = str(version) + '/'

        if authtype == 'basic':
            self.username = username
            self.password = password
            self.s.auth = (self.username, self.password)

        elif authtype == 'saml':
            self.token = token
            self.s.auth = SAMLAuth(self.token)

        elif authtype == 'jwt':
            self.username = username
            self.password = password
            token = self.getJWTtoken()
            self.token = token.tokenValue
            self.s.auth = JWTAuth(self.token)

    ######################################################
    # session management
    ########################################################
    def _validate_exp(self):
        """
        checks if the session is still valid
        :return: if validation is expired or not
        :rtype: bool
        :raises:  DecodeError
        """
        now = timegm(datetime.utcnow().utctimetuple())

        if self.authtype == 'jwt':
            if not hasattr(self, 'token'):
                # I pass here only one time, when I request a token
                self.token = None
                return True
            payload = jwt.decode(self.token, verify=False)
            try:
                exp = int(payload['exp'])
            except ValueError:
                raise jwt.DecodeError('Expiration Time claim (exp) must be an'
                                      ' integer.')

            if exp < now:
                # raise jwt.ExpiredSignatureError('Signature has expired')
                return False
            else:
                self.s.auth = JWTAuth(self.token)
                return True
        else:
            return True

    def _stayAlive(self):
        """
        checks if the token has expired, if yes, request a new token and initiates a new session
        """

        if not self._validate_exp():
            self.s.auth = JWTAuth(self.getJWTtoken().tokenValue)

    def getJWTtoken(self):
        """
        request the JWT token from the server using Basic Auth

        :return: token - a authentication token or None
        :rtype: APIToken or None
        """

        token = False
        res = self.s.get(self.url + 'tokens/jwt', auth=(self.username, self.password), verify=False)
        token = vsdModels.APIToken(**res.json())
        try:
            payload = jwt.decode(token.tokenValue, verify=False)

        except jwt.InvalidTokenError as e:
            logger.error('token invalid, try using Basic Auth{0}'.format(e))
            raise

        return token

    #################################################
    # requests library wrappers
    ################################################

    def _download(self, url, fp, onlyHeader = False):
        r = urlparse(url)
        res = self._requestsAttempts(self.s.get, r.geturl(), params=r.params, stream=True)
        try:
            filename = fp.name  # path object
        except:
            filename = fp  # string
        with open(filename, 'wb') as f:
            for n, chunk in enumerate(res.iter_content(1024)):
                f.write(chunk)
                if onlyHeader and n > 2:
                    break


    def _requestsAttempts(self, method, url, *args, **kwargs):
        #     generic wrapper around request library with multiple attempts
        #     replaces self._httpResponseCheck(self, response):
        #     :param method: string of the method to call "get", "put"
        #     :param url: full  url
        #     :param args: args for request call
        #     :param kwargs: kwargs for request call
        #     :return: request object (raise if error after self.maxAttempts)
        for i in range(self.maxAttempts):
            res = method(url, *args, **kwargs)
            try:
                self._stayAlive()
                res.raise_for_status()
                return res
            except:
                logger.info("Connection attempt %s/%s: %s %s" % (i, self.maxAttempts, res , url))
                if res.status_code == 401 and i > self.maxAttempts401:
                    raise
        # re-raise if > max attempts
        res.raise_for_status()

    def _get(self, resource, *args, **kwargs):  # reimplements VSDConnect.getRequest
        return self._requestsAttempts(self.s.get, resource, *args, **kwargs).json()

    def _put(self, resource, *args, **kwargs):  # reimplements VSDConnect.putRequest
        return self._requestsAttempts(self.s.put, resource, *args, **kwargs).json()

    def _delete(self, resource, *args, **kwargs):  # reimplements VSDConnect.postRequest
        return self._requestsAttempts(self.s.delete, resource, *args, **kwargs).json()

    def _post(self, resource, *args, **kwargs):
        # should I avoid multiplt attempts? not idempotent, no multiple  attempts
        return self._requestsAttempts(self.s.post, resource, *args, **kwargs).json()

    def _options(self, resource, *args, **kwargs):  # reimplements VSDConnect.getRequest
        return self._requestsAttempts(self.s.options, resource, *args, **kwargs).json()

    #################################################
    # api objects handling
    ################################################


    def getAPIObjectType(self, response):
        """
        create an APIObject depending on the type

        :param json response: object data
        :return: object
        :rtype: APIObject
        """

        apiObject = vsdModels.APIObject(**response)
        objectType = apiObject.type.name  # 'RawImage'
        if objectType not in dir(vsdModels):
            logger.warning("Unknown type %s" % objectType)
            return vsdModels.APIObject
        obj = getattr(vsdModels, objectType)
        return obj

    def createAPIObject(self, response=None, **kwargs):
        # convert  fields to response dict
        if response is None:
            response = kwargs
        objType = self.getAPIObjectType(response)
        return objType(**response)

    def parseUrl(self, resource, type):
        try:
            rId = int(resource)
            resource = "%s/%s" % (type, rId)
        except:
            pass
        assert type in resource
        return self.fullUrl(resource)

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

    def optionsRequest(self, resource):
        """
        generic options request function

        :param str resource: the api resource path
        :return: json data result or None
        :rtype: json or None
        """

        self._stayAlive()

        return self._options(resource)

    #################################################
    # api objects handling (READ)
    ################################################

    def getRequest(self, resource, rpp=None, page=None, include=None):
        """
        generic get request function

        :param str resource: resource path
        :param int rpp: results per page to show
        :param int page: page nr to show, starts with 0
        :param str include: option to include more informations
        :return: list of objects or None
        :rtype: json or None
        """

        params = dict([('rpp', rpp), ('page', page), ('include', include)])
        return self._get(self.fullUrl(resource), params=params)


    def downloadObject(self, obj, wp=None):
        """
        download the object into a ZIP file based on the object name and the working directory

        :param APIObject obj: object
        :param Path wp: workpath, where to store the zip
        :return: None or filename
        :rtype: str
        """

        fp = Path(obj.name).with_suffix('.zip')
        if wp:
            fp = Path(wp, fp)

        res = self._download(self.fullUrl(obj.downloadUrl), fp.name)

    def downloadObjectPreviewImages(self, object, thumbnail=True):
        field = 'thumbnailUrl' if thumbnail else 'imageUrl'
        embeddedImages = []
        for i, preview in enumerate(object.objectPreviews):
            p_obj = vsdModels.APIPreview(**self.getRequest(preview.selfUrl))
            img = self._requestsAttempts(self.s.get, getattr(p_obj, field))
            embeddedImages.append(base64.b64encode(img.content))
        return embeddedImages

    def getPaginated(self, resource):
        """
        get paginated object
        """

        res = self.getRequest(resource)
        page = vsdModels.APIPagination(**res)
        return page

    def getAllPaginated(self, resource, itemlist=list()):
        """
        returns all items as list

        :param str rource: resource path
        :param list itemlist: list of items
        :return: list of items
        :rtype: list of APIPagination objects
        """

        res = self.getRequest(resource)
        page = vsdModels.APIPagination(**res)
        for item in page.items:
            itemlist.append(item)
        if page.nextPageUrl:
            return self.getAllPaginated(page.nextPageUrl, itemlist=itemlist)
        else:
            return itemlist

    def iteratePageItems(self, page, func=dict):
        """
        returns all items as list

        :param str resource: resource path
        :param func: function for converting resource
        :return: iterator of items
        :rtype: list of dict or model object
        """

        for item in page.items:
            yield func(**item)

        if page.nextPageUrl:
            res = self.getRequest(page.nextPageUrl)
            nextPage = vsdModels.APIPagination(**res)
            for nextItem in self.iteratePageItems(nextPage, func=func):
                yield nextItem

    def iterateAllPaginated(self, resource, func=dict):
        """
        returns all items as list

        :param str resource: resource path
        :param func: function for converting resource
        :return: iterator of items
        :rtype: list of dict or model object
        """

        res = self.getRequest(resource)
        page = vsdModels.APIPagination(**res)
        for item in self.iteratePageItems(page, func):
            yield item

    def getObjects(self, idList=None):
        if idList is None:
            idList = ''
        if idList in ['', 'published', 'unpublished']:
            return self.iterateAllPaginated('objects/%s' % idList, func=self.createAPIObject)

        items = []
        for curId in idList:
            items.append(self.getObject(curId))
        return items

    def getOID(self, selfURL):
        """
        extracts the last part of the selfURL, tests if it is a number

        :param selfURL: (str) url to the object
        :return: either None if not an ID or the object ID (int)
        :raises: ValueError
        """

        selfURL_path = urllib.parse.urlsplit(selfURL).path
        oID = Path(selfURL_path).name
        try:
            r = int(oID)
        except ValueError as err:
            print('no object ID in the selfUrl {0}. Reason: {1}'.format(selfURL, err))
            r = None
        return r

    def getResourceTypeAndId(self, url):
        return url.rsplit('/', 2)[-2:]

    def _instantiateResource(self, res):
        try:
            pagination = vsdModels.APIPagination(**res)
            pagination.validate() #will fail if it doesno't have totalCount
            return pagination
        except:
            resourcetype, id = self.getResourceTypeAndId(res['selfUrl'])
            if resourcetype == 'objects':
                return self.createAPIObject(res)
            model = vsdModels.resourceTypes[resourcetype](**res)
            return model

    def getResource(self, url):
        res = self.getRequest(url)
        return self._instantiateResource(res)



    def getObject(self, resource):
        """retrieve an object based on the objectID

        :param int,str resource: (str) selfUrl of the object or the (int) object ID
        :return: the object
        :rtype: APIObject
        """
        resource = self.parseUrl(resource, 'objects')

        res = self.getRequest(resource)
        obj = self.createAPIObject(res)
        return obj

    def getFolder(self, resource):
        """retrieve an folder based on the folderID

        :param int,str resource: (str) selfUrl of the folder or the (int) folder ID
        :return: the folder
        :rtype: APIFolder
        """
        resource = self.parseUrl(resource, 'folders')
        res = self.getRequest(resource)
        folder = vsdModels.APIFolder(**res)
        return folder

    def getObjectFilesHash(self, obj):
        """
        retrieve the filehash and the anonymized file hash values of a file

        :param APIObject f: API object
        :return: list of fileHash (uppercase)
        :rtype: list of str
        """

        filehash = list()

        files = self.getObjectFiles(obj)

        for f in files:
            filehash.append(f.fileHashCode)

        return filehash

    def walkFolder(self, folderUrl, topdown=True):
        # similar to os.walk
        folderObject = self.getFolder(folderUrl)
        dirs = folderObject.childFolders
        nondirs = folderObject.containedObjects
        if dirs is None:
            dirs = []
        if nondirs is None:
            nondirs = []
        if topdown:
            yield folderObject, dirs, nondirs

        for nextDir in dirs:
            for x in self.walkFolder(nextDir.selfUrl):
                yield x
        if not topdown:
            yield folderObject, dirs, nondirs

    def checkFileInObject(self, obj, fp):
        """
        check if a local file is part of an object

        :param APIObject obj: API object
        :param Path fp: file to test
        :return: if contained or not
        :rtype: bool
        """

        containted = False
        ## Haso of all files
        filehash = self.getObjectFilesHash(obj)

        ## Local hash
        BLOCKSIZE = 65536
        hasher = hashlib.sha1()

        with fp.open('rb') as afile:
            buf = afile.read(BLOCKSIZE)
            while len(buf) > 0:
                hasher.update(buf)
                buf = afile.read(BLOCKSIZE)
        localhash = hasher.hexdigest()

        if localhash.upper() in filehash:
            containted = True

        return containted

    def searchTerm(self, resource, search, mode='default'):
        """ search a resource using oAuths

        :param str resouce: resource path
        :param str search: term to search for
        :param str mode: search for partial match (default) or exact match (exact)
        :return: list of folder objects
        :rtype: json
        """

        search = urlparse_quote(search)
        if mode == 'exact':
            url = self.fullUrl(resource) + '?$filter=Term%20eq%20%27{0}%27'.format(search)
        else:
            url = self.fullUrl(resource) + '?$filter=startswith(Term,%27{0}%27)%20eq%20true'.format(search)

        req = self.getRequest(url)

    def showObjectInformation(self, obj):
        """
        display the object information user readable format

        :param APIObject obj: object
        """

        print('---------General Information ----------')
        if obj.description is not None:
            print('description:', obj.description)
        if obj.name is not None:
            print('name: ', obj.name)
        if obj.createdDate is not None:
            print('creation date: ', obj.createdDate)
        if obj.id is not None:
            print('id: ', obj.id)
        if obj.type is not None:
            print('type: ', obj.type)

        print('todo')

        if obj.modality is not None:
            print('---------Modality----------')
            basic = vsdModels.APIBasic()
            basic.set(obj=obj.modality)
            mod = self.getModality(basic.selfUrl)

            print('name: ', mod.name)
            print('description', mod.description)
            print('selfUrl: ', mod.selfUrl)
            print('id: ', mod.id)

        if obj.ontologyItems is not None:
            print('---------Ontology items----------')
            for onto in obj.ontologyItems:
                basic = vsdModels.APIBasic()
                basic.set(obj=onto)
                ontology = self.getOntologyItem(basic.selfUrl)

                print('Term: ', ontology.term)
                print('type', ontology.type)
                print('selfUrl: ', ontology.selfUrl)
                print('id: ', ontology.id)

        if obj.license is not None:
            print('---------License----------')
            basic = vsdModels.APIBasic()
            basic.set(obj=obj.license)
            lic = self.getLicense(basic.selfUrl)
            print('name: \t\t', lic.name)
            print('description:\t', lic.description)
            print('selfUrl:\t\t', lic.selfUrl)
            print('id:\t\t\t', lic.id)

        print('---------User Rights----------')
        ur = self.getObjectUserRights(obj)
        if ur:
            for u in ur:
                user = self.getUser(u.relatedUser['selfUrl'])
                print('user:')
                print(user.to_struct())
                print('rights:')
                for r in u.relatedRights:
                    print(self.getObjectRight(r['selfUrl']).to_struct())
        else:
            print('nothing here')

        print('---------GroupRights----------')
        gr = self.getObjectGroupRights(obj)
        if gr:
            for g in gr:
                group = self.getGroup(g.relatedGroup['selfUrl'])
                print('group:')
                print(group.to_struct())
                print('rights:')
                for r in g.relatedRights:
                    print(self.getObjectRight(r['selfUrl']).to_struct())
        else:
            print('nothing here')

    def getFile(self, resource):
        """
        return a APIFile object

        :param str resource: resource path
        :return: api file object  or status code
        :rtype: APIFile
        """
        resource = self.parseUrl(resource, 'files')

        res = self.getRequest(resource)
        fObj = vsdModels.APIFile(**res)
        return fObj

    def getObjectFiles(self, obj):
        """
        return a list of file objects contained in an object

        :param APIObject obj: object
        :return: list of APIFile
        :rtype: list of APIFile
        """
        filelist = list()

        fileurl = 'objects/{0}/files'.format(obj.id)

        fl = self.iterateAllPaginated(fileurl)

        for f in fl:
            res = self.getFile(f['selfUrl'])
            filelist.append(res)
        return filelist

    def fileObjectVersion(self, data):
        """
        Extract VSDID and selfUrl of the related Object Version of the file after file upload

        :param json data: file object data
        :result: returns the id and the selfUrl of the Object Version
        :rtype: str
        """

        # data = json.loads(data)
        f = data['file']
        obj = data['relatedObject']
        fSelfUrl = f['selfUrl']
        return obj['selfUrl'], self.getOID(obj['selfUrl'])

    def getAllUnpublishedObjects(self, resource='objects/unpublished'):
        """ retrieve the unpublished objects as list of APIObject

        :param str resource: resource path (eg nextPageUrl) or default groups
        :param int rpp: results per page
        :param int page: page to display
        :return: list of objects
        :rtype: APIObjects
        """

        objects = list()

        for item in self.iterateAllPaginated(resource, vsdModels.APIObject):
            obj = self.getObject(item.selfUrl)
            objects.append(obj)
        return objects

    def getLatestUnpublishedObject(self):
        """
        searches the list of unpublished objects and returns the newest object

        :return: last uploaded object
        :rtype: apiObject
        """

        res = self.getRequest('objects/unpublished')

        if len(res['items']) > 0:
            obj = self.getObject(res['items'][0].get('selfUrl'))
            return obj
        else:
            print('you have no unpublished objects')
            return None

    def getFolderByName(self, search, mode='default', squeeze=True):
        """
        get a list of folder(s) based on a search string

        :param str search: term to search for
        :param str mode: search for partial match ('default') or exact match ('exact')
        :return: list of folder objects APIFolders
        :rtype: list of APIFolders
        """

        search = urlparse_quote(search)

        if mode == 'exact':

            url = self.url + "folders?$filter=Name%20eq%20%27{0}%27".format(search)

        else:

            url = self.url + "folders?$filter=startswith(Name,%27{0}%27)%20eq%20true".format(search)

        result = list(self.iterateAllPaginated(url, vsdModels.APIFolder))

        if len(result) == 1 and squeeze:
            folder = result[0]
            print('1 folder matching the search found')
            return folder

        else:
            print('list of {} folders matching the search found'.format(len(result)))
            return result

    def getContainedFolders(self, folder):
        """
        return a list of folder object contained in a folder

        :param APIFolder folder: folder object
        :return folderlist: a list of folder object (APIFolder) contained in the folder
        :rtype: list of APIFolder
        """

        folderlist = list()
        if folder.childFolders:

            for fold in folder.childFolders:
                basic = vsdModels.APIBasic(**fold)
                f = self.getFolder(basic.selfUrl)
                folderlist.append(f)
            return folderlist
        else:
            print('the folder does not have any contained folders')
            return None

    def getContainedObjects(self, folder):
        """
        return a list of object contained in a folder

        :param APIFolder folder: folder object
        :return objlist: a list of objects (APIFObject) contained in the folder
        :rtype:  list of APIObject
        """

        objlist = list()

        if folder.containedObjects:

            for obj in folder.containedObjects:
                basic = vsdModels.APIBasic(**obj)
                o = self.getObject(basic.selfUrl)
                objlist.append(o)
            return objlist
        else:
            print('the folder does not have any contained objects')
            return None

    def getModalityList(self):
        """
        retrieve a list of modalities objects (APIModality)

        :return: list of available modalities
        :rtype: list of APIModality
        """

        modalities = list()
        items = self.iterateAllPaginated('modalities')
        if items:
            for item in items:
                modality = vsdModels.APIModality(**item)
                modalities.append(modality)
        return modalities

    def getModality(self, resource):
        """ retrieve a modalities object (APIModality)


        :param int,str resource: resource path to the of the modality
        :return: the modality object
        :rtype: APIModality
        """

        resource = self.parseUrl(resource, 'modalities')

        res = self.getRequest(resource)
        mod = vsdModels.APIModality(**res)

    def readFolders(self, folderList):
        # first pass: create one entry for each folder:
        folderHash = {}
        for folder in folderList['items']:
            ID = folder['id']
            folderHash[ID] = vsdModels.APIFolder()
            folderHash[ID].ID = ID
            folderHash[ID].name = folder['name']
            folderHash[ID].childFolders = []

            # second pass: create references to parent and child folders
        for folder in folderList['items']:
            ID = folder['id']
            if (folder['childFolders'] != None):
                # print (folder['childFolders'],ID)
                for child in folder['childFolders']:
                    childID = int(child['selfUrl'].split("/")[-1])
                    if (folderHash.has_key(childID)):
                        folderHash[ID].childFolders.append(folderHash[childID])
            if (folder['parentFolder'] != None):
                parentID = int(folder['parentFolder']['selfUrl'].split("/")[-1])
                if (folderHash.has_key(parentID)):
                    folderHash[ID].parentFolder = folderHash[parentID]
            if (not folder['containedObjects'] == None):
                folderHash[ID].containedObjects = {}
                for obj in folder['containedObjects']:
                    objID = obj['selfUrl'].split("/")[-1]
                    folderHash[ID].containedObjects[objID] = obj['selfUrl']

        # third pass: gett full path names in folder hierarchy
        for key, folder in folderHash.iteritems():
            folder.getFullName()

        return folderHash

    def getFolderContent(self, folder, recursive=False, mode='d'):
        """
        get the objects and folder contained in the given folder. can be called recursive to travel and return all objects

        :param APIFolder folder: the folder to be read
        :param bool recursive:  travel the folder structure recursively or not (default)
        :param str mode: what to return: only objects (o), only folders (f) or default (d) folders and objects
        :return content: dictionary with folders (APIFolder) and object (APIObjects)
        :rtype: dict of APIFolder and APIObject
        """

        objectmode = False
        foldermode = False

        if mode == 'o':
            objectmode = True

        elif mode == 'f':
            foldermode = True

        elif mode == 'd':
            objectmode = True
            foldermode = True
        else:
            print('mode {0} not supported'.format(mode))

        folders = self.getContainedFolders(folder)

        temp = dict([('folder', folder), ('object', None)])

        if foldermode:
            content = list([temp])
        else:
            content = list()

        if objectmode:
            objects = self.getContainedObjects(folder)

            if objects is not None:
                for obj in objects:
                    temp = dict([('folder', folder), ('object', obj)])
                    content.append(temp)

        if folders is not None:
            if recursive:
                for fold in folders:
                    content.extend(self.getFolderContent(fold, mode=mode, recursive=True))

            else:
                if foldermode:
                    for fold in folders:
                        temp = dict([('folder', folder), ('object', None)])
                        content.append(temp)

        return content

    def searchOntologyTerm(self, search, oType='0', mode='default'):
        """
        Search ontology term in a single ontology resource. Two modes are available to either find the exact term or based on a partial match

        :param str search: string to be searched
        :param int oType: ontlogy resouce code, default is FMA (0)
        :param str mode: find exact term (exact) or partial match (default)
        :returns: a list of ontology objects or a single ontology item
        :rtype: APIOntolgy
        """
        search = urlparse_quote(search)
        if mode == 'exact':
            url = self.url + "ontologies/{0}?$filter=Term%20eq%20%27{1}%27".format(oType, search)
        else:
            url = self.url + "ontologies/{0}?$filter=startswith(Term,%27{1}%27)%20eq%20true".format(oType, search)

        res = self._get(url)
        if res.status_code == requests.codes.ok:
            result = list()

            res = res.json()

            if len(res['items']) == 1:
                onto = vsdModels.APIOntology()
                onto.set(res['items'][0])
                print('1 ontology term matching the search found')
                return onto
            for item in iter(res['items']):
                onto = vsdModels.APIOntology()
                onto.set(item)
                result.append(onto)
            return result
        else:
            return res.status_code

    def getOntologyTermByID(self, oid, oType=0):
        """
        Retrieve an ontology entry based on the IRI

        :param int oid: Identifier of the entry
        :param int oType: Resource type, available resources can be found using the OPTIONS on /api/ontologies). Default resouce is FMA (0)
        :return: ontology term entry
        :rtype: json
        """

        url = "ontologies/{0}/{1}".format(oType, oid)
        req = self.getRequest(url)
        return req.json()

    def getOntologyItem(self, resource, oType=0):
        """
        Retrieve an ontology item object (APIOntology)

        :param int,str resource: resource path to the of the ontology item
        :param int oType: ontology type
        :return onto: the ontology item object
        :rtype: APIOntology
        """

        if isinstance(resource, int):
            resource = 'ontology/{0}/{1}'.format(resource, oType)

        res = self.getRequest(resource)
        onto = vsdModels.APIOntology(**res)

        return onto

    def getLicenseList(self):
        """ retrieve a list of the available licenses (APILicense)


        :return: list of available license objects
        :rtype: list of APILicense
        """

        res = self.getRequest('licenses')
        licenses = list()
        if res:
            for item in iter(res['items']):
                lic = vsdModels.APILicense(**item)
                licenses.append(lic)

        return licenses

    def getLicense(self, resource):
        """ retrieve a license (APILicense)

        :param int,str resource: resource path to the of the license
        :return license: the license object
        :rtype: APILicense
        """

        if isinstance(resource, int):
            resource = 'licenses/{0}'.format(resource)

        res = self.getRequest(resource)
        if res:
            license = vsdModels.APILicense(**res)

            return license
        else:
            return None

    def getObjectRightList(self):
        """ retrieve a list of the available base object rights (APIObjectRight)

        :return: list of object rights
        :rtype: list of APIObjectRight
        """

        res = self.getRequest('object_rights')
        permission = list()

        if res:
            for item in iter(res['items']):
                perm = vsdModels.APIObjectRight(**item)
                permission.append(perm)

        return permission

    def getObjectRight(self, resource):
        """ retrieve a  object rights object (APIObjectRight)

        :param int,str resource: resource to the permission id (int) or selfurl (str)
        :return: perm object
        :rtype: APIObjectRight
        """

        if isinstance(resource, int):
            resource = 'object_rights/{0}'.format(resource)
        res = self.getRequest(resource)

        if res:
            perm = vsdModels.APIObjectRight()
            perm.set(obj=res)
            return perm
        else:
            return None

    def getGroups(self, resource='groups', rpp=None, page=None):
        """get the list of groups

        :param str resource: resource path (eg nextPageUrl) or default groups
        :param int rpp: results per page
        :param int page: page number to display
        :return: list of group objects
        :rtype: APIGroup
        :return: pagination object
        :rtype: APIPagination
        """

        groups = list()
        res = self.getRequest(resource, rpp, page)
        ppObj = vsdModels.APIPagination(**res)

        for g in ppObj.items:
            group = vsdModels.APIGroup(**g)
            groups.append(group)

        return groups, ppObj

    def getGroup(self, resource):
        """ retrieve a group object (APIGroup)

        :param int,str resource: path to the group id (int) or selfUrl (str)
        :return: group  object
        :rtype: APIGroup
        """

        if isinstance(resource, int):
            resource = 'groups/{0}'.format(resource)

        res = self.getRequest(resource)

        if res:
            group = vsdModels.APIGroup()
            group.set(obj=res)
            return group
        else:
            return None

    def getUser(self, resource):
        """ retrieve a user object (APIUser)

        :param int,str resource: path to the user resource id (int) or selfUrl (str)
        :return: user object
        :rtype: APIUser
        """
        if isinstance(resource, int):
            resource = 'users/{0}'.format(resource)

        res = self.getRequest(resource)

        if res:
            user = vsdModels.APIUser(**res)
            return user
        else:
            return None

    def getPermissionSets(self, permset='default'):
        """
        get the Object Rights for a permission set

        :param str permset: name of the permission set: available are private, protect, default, collaborate, full or a list of permission ids (list)
        :return perms: list of object rights objects
        :rtype: APIObjectRight
        """

        if permset == 'private':
            lperms = list([1])
        elif permset == 'protect':
            lperms = list([2, 3])
        elif permset == 'default':
            lperms = list([2, 3, 4])
        elif permset == 'collaborate':
            lperms = list([2, 3, 4, 5])
        elif permset == 'full':
            lperms = list([2, 3, 4, 5, 6])
        else:
            lperms = permset

        perms = list()
        for pid in lperms:
            perms.append(self.getObjectRight(pid))

        return perms

    def getObjectGroupRights(self, obj):
        """
        get the list of attaced group rights of an object

        :param APIObject obj: the object
        :return rights: a list of ObjectGroupRights
        :rtype: list of APIObjectGroupRight
        """

        rights = None
        if obj.objectGroupRights:
            rights = list()
            for item in obj.objectGroupRights:
                res = self.getRequest(item['selfUrl'])
                right = vsdModels.APIObjectGroupRight()
                right.set(obj=res)
                rights.append(right)

        return rights

    def getObjectUserRights(self, obj):
        """
        get the list of attaced user rights of an object

        :param APIObject obj: the object
        :return: a list of ObjectUserRights
        :rtype: list APIObjectUserRight
        """

        rights = None
        if obj.objectUserRights:
            rights = list()
            for item in obj.objectUserRights:
                res = self.getRequest(item['selfUrl'])
                right = vsdModels.APIObjectUserRight()
                right.set(obj=res)
                rights.append(right)

        return rights

    #################################################
    # api objects handling (MODIFY)
    ################################################
    def postRequest(self, resource, data):
        """add data to an object

        :param str resource: relative path of the resource or selfUrl
        :param json data: data to be added to the resource
        :return: the resource object
        :rtype: json
        :raises: RequestException
        """

        return self._post(self.fullUrl(resource), json=data)

    def removeLinks(self, resource):
        """
        removes all related item from an object

        :param str resource: resouce path url
        :return: True if successful or False if failed
        :rtype: bool
        """

        obj = self.getObject(resource)
        if obj.linkedObjectRelations:
            for link in self.iteratePageItems(obj.linkedObjectRelations, vsdModels.APIObjectLink):
                print(link)
                self.delRequest(link.selfUrl)
        else:
            print('nothing to delete, no links available')

    def delRequest(self, resource):
        """
        generic delete request

        :param str resource: resource path
        :return: status_code
        :rtype: int
        """

        try:
            req = self.s.delete(self.fullUrl(resource))
            if req.status_code == requests.codes.ok:
                print('resource {0} deleted, 200'.format(self.fullUrl(resource)))
                return req.status_code
            elif req.status_code == requests.codes.no_content:
                print('resource {0} deleted, 204'.format(self.fullUrl(resource)))
                return req.status_code
            else:
                print('resource {0} NOT (not existing or other problem) deleted'.format(self.fullUrl(resource)))
                return req.status_code

        except requests.exceptions.RequestException as err:
            print('del request failed:', err)
            return

    def delObject(self, obj):
        """
        delete an unvalidated object

        :param APIObject obj: the object to delete
        :return: status_code
        :rtype: int
        """

        try:
            req = self.s.delete(obj.selfUrl)
            if req.status_code == requests.codes.ok:
                print('object {0} deleted'.format(obj.id))
                return req.status_code
            else:
                return req.status_code
                print('not deleted', req.status_code)

        except requests.exceptions.RequestException as err:
            print('del request failed:', err)

    def chunkedread(self, fp, chunksize):
        """
        breaks the file into chunks of chunksize

        :param Path fp: the file to chunk
        :param int chunksize: size in bytes of the chunk parts
        :yields: chunk
        """

        with fp.open('rb') as f:
            while True:
                chunk = f.read(chunksize)
                if not chunk:
                    break
                yield (chunk)

    def chunkFileUpload(self, fp, chunksize=1024 * 4096):
        """
        upload large files in chunks of max 100 MB size

        :param Path fp: the file to upload
        :param int chunksize: size in bytes of the chunk parts, default is 4MB
        :return: the generated object
        :rtype: APIObject
        """
        parts = int(math.ceil(fp.stat().st_size / float(chunksize)))
        err = False
        maxchunksize = 1024 * 1024 * 100
        if chunksize >= maxchunksize:
            print(
                'not uploaded: defined chunksize {0} is bigger than the allowed maximum {1}'.format(chunksize, maxchunksize))
            return None

        part = 0
        for part, chunk in enumerate(self.chunkedread(fp, chunksize),1):
            logger.info('({2})uploading part {0} of {1}'.format(part, parts, fp.name))
            files = {'file': (str(fp.name), chunk)}
            res = self._post(self.fullUrl('/chunked_upload?chunk={0}').format(part), files=files)

        print('finish, uploaded part {0} of {1} '.format(part, parts))
        res = self._post(self.fullUrl('chunked_upload/commit?filename={0}'.format(fp.name)))
        return self.getFile(res['file']['selfUrl']), self.getObject(res['relatedObject']['selfUrl'])

        # relObj = res['relatedObject']
        # obj = self.getObject(relObj['selfUrl'])
        # return obj



    def postFolder(self, parent, name, check=True):
        """
        creates the folder with a given name (name) inside a folder (parent) if not already exists

        :param APIFolder parent: the root folder
        :param str name: name of the folder which should be created
        :param bool check: it we should check if already exist, default = True
        :return: the folder object of the generated folder or the existing folder
        :rtype: APIFolder
        """

        folder = vsdModels.APIFolder()
        if parent is None:
            parent = self.getFolderByName('MyProjects', mode='exact')
        folder.parentFolder = vsdModels.APIBasic(selfUrl=parent.selfUrl)
        folder.name = name

        exists = False

        if check:
            if parent.childFolders:
                for child in parent.childFolders:
                    fold = self.getFolder(child.selfUrl)
                    if fold is not None:
                        if fold.name == name:
                            print('folder {0} already exists, id: {1}'.format(name, fold.id))
                            exists = True
                            return fold
                    else:
                        print('unexpected error, folder exists but cannot be retrieved')
                        exists = True

        # print(self.postRequest('folders', data = data))
        if not exists:
            data = folder.to_struct()
            # for name, field in folder:
            #     if name not in data:
            #         data[name] = None
            # print(data)
            res = self.postRequest('folders', data=data)
            folder.populate(**res)
            print('folder {0} created, has id {1}'.format(name, folder.id))
            assert folder.name == name
            return folder

    def uploadFile(self, filename):
        """
        push (post) a file to the server

        :param Path filename: the file to be uploaded
        :return: the file object containing the related object selfUrl
        :rtype: APIObject
        """

        try:
            data = filename.open(mode='rb').read()
            ##workaround for file without file extensions
            if filename.suffix == '':
                filename = filename.with_suffix('.dcm')
            files = {'file': (str(filename.name), data)}
        except:
            print("opening file", filename, "failed, aborting")
            return

        res = self._post(self.url + 'upload', files=files)
        return self.getFile(res['file']['selfUrl']), self.getObject(res['relatedObject']['selfUrl'])


    #################################################
    # api objects handling (UPDATE)
    ################################################
    def putObject(self, obj):
        """update an objects information

        :param APIObject obj: an APIObject
        :return: the updated object
        :rtype: APIObject
        """

        res = self.putRequest(obj.selfUrl, data=obj.to_struct())

        if res:
            obj = self.createAPIObject(res)
            return obj
        else:
            return res

    def putRequest(self, resource, data):
        """ update data of an object

        :param str resource: defines the relative path to the api resource
        :param json data: data to be added to the object
        :return: the updated object
        :rtype: json
        """

        try:
            req = self._put(self.fullUrl(resource), json=data)
            return req
        except requests.exceptions.RequestException as err:
            print('request failed:', err)
            return None

    def postRequestSimple(self, resource):
        """
        post (create) a resource

        :param str resource: resource path
        :return: the resource object
        :rtype: json
        """

        req = self.s.post(self.fullUrl(resource))
        return req.json()

    def putRequestSimple(self, resource):
        """
        put (update) a resource

        :param str resource: resource path
        :return: the resource object
        :rtype: json
        """

        req = self.s.put(self.fullUrl(resource))
        return req.json()

    def publishObject(self, obj):
        """
        publisch an unvalidated object

        :param APIObject obj: the object to publish
        :return: returns the object
        :rtype: APIObject
        """

        try:
            req = self.s.put(obj.selfUrl + '/publish')
            if req.status_code == requests.codes.ok:
                print('object {0} published'.format(obj.id))
                return self.getObject(obj.selfUrl)


        except requests.exceptions.RequestException as err:
            print('publish request failed:', err)

    def deleteFolderContent(self, folder):
        """ delete all content from a folder (APIFolder)

        :param APIFolder folder: a folder object
        :return state: returns true if successful, else False
        :rtype: bool
        """

        state = False

        folder.containedObjects = None

        res = self.putRequest('folders', data=folder.to_struct())

    def postObjectRights(self, obj, group, perms, isuser=False):
        """
        translate a set of permissions and a group into the appropriate format and add it to the object


        .. warning:: DEPRECATED: use postObjectGroupRights or postObjectUserRights!


        :param APIObject obj: () the object you want to add the permissions to
        :param APIGroup/APIUser group: group object or user object
        :param list perms: list of Object Rights (APIObjectRight), use getPermissionSet to retrive the ObjectRights based on the permission sets
        :param bool isuser: set True if the groups variable is a user. Default is False
        :return: a group or user rights object
        :rtype: APIObjectGroupRight,APIObjectUserRight
        """

        # creat the dict of rights
        rights = list()
        for perm in perms:
            rights.append(dict([('selfUrl', perm.selfUrl)]))

        if isuser:
            objRight = vsdModels.APIObjectUserRight()
            objRight.relatedObject = dict([('selfUrl', obj.selfUrl)])
            objRight.relatedRights = rights
            objRight.relatedUser = dict([('selfUrl', group.selfUrl)])
            res = self.postRequest('object-user-rights', data=objRight.to_struct())
            objRight.set(res)

        else:
            objRight = vsdModels.APIObjectGroupRight()
            objRight.relatedObject = dict([('selfUrl', obj.selfUrl)])
            objRight.relatedRights = rights
            objRight.relatedGroup = dict([('selfUrl', group.selfUrl)])
            res = self.postRequest('object-group-rights', data=objRight.to_struct())
            objRight.set(res)
        return objRight

    def postObjectUserRights(self, obj, user, perms):
        """ translate a set of permissions and a user into the appropriate format and add it to the object

        :param APIObject obj: the object you want to add the permissions to
        :param APIUser user: user object
        :param list perms: list of Object Rights (APIObjectRight), use getPermissionSet to retrive the ObjectRights based on the permission sets
        :return: user rights object
        :rtype: APIObjectUserRight
        """

        # creat the dict of rights
        rights = list()
        for perm in perms:
            rights.append(dict([('selfUrl', perm.selfUrl)]))

        objRight = vsdModels.APIObjectUserRight()
        objRight.relatedObject = dict([('selfUrl', obj.selfUrl)])
        objRight.relatedRights = rights
        objRight.relatedUser = dict([('selfUrl', user.selfUrl)])

        res = self.postRequest('object-user-rights', data=objRight.to_struct())
        objRight.set(res)

        return objRight

    def postObjectGroupRights(self, obj, group, perms):
        """ translate a set of permissions and a group into the appropriate format and add it to the object

        :param APIObject obj: the object you want to add the permissions to
        :param APIGroup group: group object
        :param list perms: list of Object Rights (APIObjectRight), use getPermissionSet to retrive the ObjectRights based on the permission sets
        :return: group rights object
        :rtype: APIObjectGroupRight
        """

        # creat the dict of rights
        rights = list()

        for perm in perms:
            rights.append(dict([('selfUrl', perm.selfUrl)]))

        objRight = vsdModels.APIObjectGroupRight()
        objRight.relatedObject = dict([('selfUrl', obj.selfUrl)])
        objRight.relatedRights = rights
        objRight.relatedGroup = dict([('selfUrl', group.selfUrl)])

        res = self.postRequest('object-group-rights', data=objRight.to_struct())
        objRight.set(res)

        return objRight

    def addLink(self, obj1, obj2):
        """ add an object link

        :param APIBasic obj1: a linked object with selfUrl
        :param APIBasic obj2: a linked object with selfUrl
        :return: the created object-link
        :rtype: json
        """

        link = vsdModels.APIObjectLink(object1 =obj1, object2 = obj2)
        link.validate()
        return self.postRequest('object-links', data=link.to_struct())

    def addOntologyToObject(self, obj, ontology, pos=0):
        """ add an ontoly term to an object

        :param APIBasic obj: basic object
        :param APIOntology ontology: ontology object
        :param int pos: position of the ontology term, default = 1
        :return: returns true if successfully added
        :rtype: bool
        """

        isset = False
        if isinstance(pos, int):
            onto = vsdModels.APIObjectOntology()
            onto.position = pos
            onto.object = dict([('selfUrl', obj.selfUrl)])
            onto.ontologyItem = dict([('selfUrl', ontology.selfUrl)])
            onto.type = ontology.type

            res = self.postRequest('object-ontologies/{0}'.format(ontology.type), data=onto.to_struct())
            if res:
                isset = True
        else:
            print('position needs to be a number (int)')

        return isset

    def deleteFolder(self, folder, recursive=False):
        """remove a folder (APIFolder)

        :param APIFolder folder: the folder object
        :return: True if deleted, False if not
        :rtype: bool
        """

        state = False
        self.deleteFolderContent(folder)
        res = self.delRequest(folder.selfUrl)
        if res == 200 or res == 204:
            state = True
        if recursive:
            folders = self.getContainedFolders(folder)
            for f in folders:
                return self.deleteFolder(f, recursive=recursive)
        return state

    def createFolderStructure(self, rootfolder, filepath, parents):
        """
        creates the folders based on the filepath if not already existing,
        starting from the rootfolder

        :param APIFolder rootfolder: the root folder object
        :param Path filepath: filepath of the file
        :param int parents: number of partent levels to create from file folder
        :return: the last folder in the tree
        :rtype: APIFolder
        """

        fp = filepath.resolve()
        folders = list(fp.parts)
        folders.reverse()

        ##remove file from list
        if fp.is_file():
            folders.remove(folders[0])

        for i in range(parents, len(folders)):
            folders.remove(folders[i])

        folders.reverse()
        fparent = rootfolder

        if fparent:
            for fname in folders:
                fchild = None
                if fparent:
                    if fparent.childFolders:
                        for child in fparent.childFolders:
                            fold = self.getFolder(child.selfUrl)
                            if fold.name == fname:
                                fchild = fold
                if not fchild:
                    f = vsdModels.APIFolder()
                    f.name = fname
                    f.parentFolder = vsdModels.APIFolder(selfUrl=fparent.selfUrl)
                    # f.toJson()
                    res = self.postRequest('folders', f.to_struct())
                    fparent.populate(**res)

                else:
                    fparent = fchild

            return fparent
        else:
            print('Root folder does not exist', rootfolder)
            # jData = jFolder(folder)
            return None

    def addObjectToFolder(self, target, obj):
        """
        add an object to the folder

        :param APIFolder target: the target folder
        :param APIObject obj: the object to copy
        :return: updated folder
        :rtype: APIFolder
        """

        objSelfUrl = vsdModels.APIBasic(**obj.to_struct())

        if not objSelfUrl in target.containedObjects:
            target.containedObjects.append(objSelfUrl)
            res = self.putRequest('folders', data=target.to_struct())

            target = vsdModels.APIFolder(**res)
            return target

        else:
            return target

    def removeObjectFromFolder(self, target, obj):
        """
        remove an object from the folder

        :param APIFolder target: the target folder
        :param APIObject obj: the object to remove
        :return: updated folder
        :rtype: APIFolder
        """

        objSelfUrl = dict([('selfUrl', obj.selfUrl)])
        objects = target.containedObjects

        isset = False

        if objects:
            if objects.count(objSelfUrl) > 0:
                objects.remove(objSelfUrl)
                target.containedObjects = objects
                res = self.putRequest('folders', data=target.to_struct())

                if not isinstance(res, int):
                    isset = True
            else:
                print('object not part of that folder')
        else:
            print('folder containes no objects')

        return isset
