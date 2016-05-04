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

import sys
import math
import hashlib

from datetime import datetime
from calendar import timegm

if sys.version_info >= (3, 0):
    PYTHON3 = True
else:
    PYTHON3 = False

import os
import urllib
import jwt
if PYTHON3:
    from urllib.parse import urlparse
    from urllib.parse import quote as urlparse_quote
else:
    from urlparse import urlparse
    from urllib import quote as urlparse_quote

import json
import getpass
if PYTHON3:
    from pathlib import Path, PurePath, WindowsPath
import requests
from requests.auth import AuthBase

import io
import base64
import zlib
import zipfile
import shutil

try:
    import lxml.etree as ET
except:
    import xml.etree.ElementTree as ET




requests.packages.urllib3.disable_warnings()

class SAMLAuth(AuthBase):
    """Attaches SMAL to the given Request object. extends the request package auth class"""
    def __init__(self, enctoken):
        self.enctoken = enctoken

    def __call__(self, r):
        # modify and return the request
        r.headers['Authorization'] = b'SAML auth=' + self.enctoken
        return r

def samltoken(fp, stsurl = 'https://ciam-dev-chic.custodix.com/sts/services/STS'):
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
        authdata =  ET.tostring(dom, encoding = 'utf-8')

    #send the xml in the attachment to https://ciam-dev-chic.custodix.com/sts/services/STS
    r = requests.post(stsurl, data = authdata, verify = False)

    if r.status_code == 200:

        fileobject = io.BytesIO(r.content)

        tree = ET.ElementTree()
        dom = tree.parse(fileobject)
        saml = ET.tostring(dom, method = "xml", encoding = "utf-8")


        #ZLIB (RFC 1950) compress the retrieved SAML token.
        ztoken = zlib.compress(saml, 9)

        #Base64 (RFC 4648) encode the compressed SAML token.
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
    __APIURL='https://demo.virtualskeleton.ch/api/'

    def __init__(
        self,
        authtype = 'jwt',
        url = "https://demo.virtualskeleton.ch/api/",
        username = "demo@virtualskeleton.ch",
        password = "demo",
        version = "",
        token = None,
        ):

        self.version = version
        self.url = url + version
        self.s = requests.Session()
        self.s.verify = False
        self.authtype = authtype


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




    def _httpResponseCheck(self, response):
        """
        check the response of a request call to the resouce.
        """

        try:
            response.raise_for_status()
            return True, response.status_code

        except requests.exceptions.HTTPError as e:
            print("And you get an HTTPError: {0}".format(e))
            return False, response.status_code

    def _validate_exp(self):
        """
        checks if the session is still valid
        :return: if validation is expired or not
        :rtype: bool
        :raises:  DecodeError
        """
        now = timegm(datetime.utcnow().utctimetuple())

        if self.authtype == 'jwt':
            payload = jwt.decode(self.token, verify = False)
            try:
                exp = int(payload['exp'])
            except ValueError:
                raise jwt.DecodeError('Expiration Time claim (exp) must be an'
                                  ' integer.')

            if exp < now :
                #raise jwt.ExpiredSignatureError('Signature has expired')
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
        res = requests.get(self.url + 'tokens/jwt', auth = (self.username, self.password), verify = False)

        if self._httpResponseCheck(res)[0]:

            token = APIToken()
            token.set(obj = res.json())
            try:
                payload = jwt.decode(token.tokenValue, verify = False)

            except jwt.InvalidTokenError as e:
                print('token invalid, try using Basic Auth{0}'.format(e))

        return token

    def getAPIObjectType(self, response):
        """
        create an APIObject depending on the type

        :param json response: object data
        :return: object
        :rtype: APIObject
        """
        apiObject = APIObject()
        apiObject.set(obj = response)
        objectType = APIObjectType()
        objectType.set(obj = apiObject.type)

        if objectType.name == 'RawImage':
            obj = APIObjectRaw()
        elif objectType.name == 'SegmentationImage':
            obj = APIObjectSeg()
        elif objectType.name == 'StatisticalModel':
            obj = APIObjectSm()
        elif objectType.name == 'ClinicalStudyDefinition':
            obj = APIObjectCtDef()
        elif objectType.name == 'ClinicalStudyData':
            obj = APIObjectCtData()
        elif objectType.name == 'SurfaceModel':
            obj = APIObjectSurfModel()
        elif objectType.name == 'GenomicPlatform':
            obj = APIObjectGenPlatform()
        elif objectType.name == 'GenomicSample':
            obj = APIObjectGenSample()
        elif objectType.name == 'GenomicSeries':
            obj = APIObjectGenSeries()
        elif objectType.name == 'Study':
            obj = APIObjectStudy()
        elif objectType.name == 'Subject':
            obj = APIObjectSubject()
        elif objectType.name == 'Plain':
            obj = APIObject()
        elif objectType.name == 'PlainSubject':
            obj = APIObject()
        else:
            obj = APIObject()
        return obj


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

        try:
            res = self.s.options(self.fullUrl(resource))
            if self._httpResponseCheck(res):
                if res.status_code == requests.codes.ok:
                    return res.json()
                else:
                    return None
        except requests.exceptions.RequestException as err:
            print('option request failed:', err)
            return None

    def getRequest(self, resource, rpp = None, page = None, include = None):
        """
        generic get request function

        :param str resource: resource path
        :param int rpp: results per page to show
        :param int page: page nr to show, starts with 0
        :param str include: option to include more informations
        :return: list of objects or None
        :rtype: json or None
        """

        params = dict([('rpp', rpp),('page', page),('include', include)])

        self._stayAlive()

        try:

            res = self.s.get(self.fullUrl(resource), params = params)

            if self._httpResponseCheck(res):
                if res.status_code == requests.codes.ok:
                    return res.json()
                else:
                    return None
        except requests.exceptions.RequestException as err:
            print('request failed:', err)
            return None

    def downloadZip(self, resource, fp):
        """
        download the zipfile into the given file (fp)

        :param str resource: download URL
        :param Path fp:  filepath
        :return: None or status_code ok (200)
        :rtype: int
        """

        self._stayAlive()

        res = self.s.get(self.fullUrl(resource), stream = True)
        if res.ok:
            with fp.open('wb') as f:
                shutil.copyfileobj(res.raw, f)
            return res.status_code
        else:
            return None

    def downloadObject(self, obj, wp = None):
        """
        download the object into a ZIP file based on the object name and the working directory

        :param APIObject obj: object
        :param Path wp: workpath, where to store the zip
        :return: None or filename
        :rtype: str
        """

        self._stayAlive()

        fp = Path(obj.name).with_suffix('.zip')
        if wp:
            fp = Path(wp, fp)

        res = self.s.get(self.fullUrl(obj.downloadUrl), stream = True)
        if res.ok:
            with fp.open('wb') as f:
                shutil.copyfileobj(res.raw, f)
            return fp
        else:
            return None


    def removeLinks(self, resource):
        """
        removes all related item from an object

        :param str resource: resouce path url
        :return: True if successful or False if failed
        :rtype: bool
        """

        obj = self.getObject(resource)
        status = False
        if obj.linkedObjectRelations:
            for link in obj.linkedObjectRelations:
                self.delRequest(link["selfUrl"])
        else:
            print('nothing to delete, no links available')

    def getPaginated(self, resource):
        """ 
        get paginated object
        """
        res = self.getRequest(resource)
        if res:
            page = APIPagination()
            page.set(obj = res)

        else:
            page = None

        return page

    def getAllPaginated(self, resource, itemlist = list()):
        """
        returns all items as list

        :param str rource: resource path
        :param list itemlist: list of items
        :return: list of items
        :rtype: list of APIPagination objects
        """

        res = self.getRequest(resource)
        if res:
            page = APIPagination()
            page.set(obj = res)
            for item in page.items:
                itemlist.append(item)
            if page.nextPageUrl:
                return self.getAllPaginated(page.nextPageUrl, itemlist = itemlist)
            else:
                return itemlist
        else:
            return itemlist

    def getOID(self, selfURL):
        """
        extracts the last part of the selfURL, tests if it is a number

        :param selfURL: (str) url to the object
        :return: either None if not an ID or the object ID (int)
        :raises: ValueError
        """

        selfURL_path = urllib.parse.urlsplit(selfURL).path
        if PYTHON3:
            oID = Path(selfURL_path).name
        else:
            oID = os.path.basename(selfURL_path)

        try:
            r = int(oID)
        except ValueError as err:
            print('no object ID in the selfUrl {0}. Reason: {1}'.format(selfURL,err))
            r = None
        return r

    def getObject(self, resource):
        """retrieve an object based on the objectID

        :param int,str resource: (str) selfUrl of the object or the (int) object ID
        :return: the object
        :rtype: APIObject
        """
        if isinstance(resource, int):
            resource = 'objects/' + str(resource)

        res = self.getRequest(resource)
        if res:
            obj = self.getAPIObjectType(res)
            obj.set(obj = res)
            return obj
        else:
            return res

    def putObject(self, obj):
        """update an objects information

        :param APIObject obj: an APIObject
        :return: the updated object
        :rtype: APIObject
        """

        res = self.putRequest(obj.selfUrl, data = obj.get())

        if res:
            obj = self.getAPIObjectType(res)
            obj.set(obj = res)
            return obj
        else:
            return res

    def getFolder(self, resource):
        """retrieve an folder based on the folderID

        :param int,str resource: (str) selfUrl of the folder or the (int) folder ID
        :return: the folder
        :rtype: APIFolder
        """
        if isinstance(resource, int):
            resource = 'folders/' + str(resource)

        res = self.getRequest(resource)

        if res:
            folder = APIFolder()
            folder.set(obj = res)
            return folder
        else:
            return res


    def postRequest(self, resource, data):
        """add data to an object

        :param str resource: relative path of the resource or selfUrl
        :param json data: data to be added to the resource
        :return: the resource object
        :rtype: json
        :raises: RequestException
        """

        self._stayAlive()

        try:
            req = self.s.post(self.fullUrl(resource), json = data)
            print('status code:', req.status_code)
            #if req.status_code == requests.codes.created:
            return req.json()
        except requests.exceptions.RequestException as err:
            print('request failed:',err)
            return None


    def putRequest(self, resource, data):
        """ update data of an object

        :param str resource: defines the relative path to the api resource
        :param json data: data to be added to the object
        :return: the updated object
        :rtype: json
        """

        self._stayAlive()

        try:
            req = self.s.put(self.fullUrl(resource), json = data)
            if req.status_code == requests.codes.ok:
                return req.json()
            else:
                return None
        except requests.exceptions.RequestException as err:
            print('request failed:',err)
            return None


    def postRequestSimple(self, resource):
        """
        post (create) a resource

        :param str resource: resource path
        :return: the resource object
        :rtype: json
        """

        self._stayAlive()

        req = self.s.post(self.fullUrl(resource))
        return req.json()

    def putRequestSimple(self, resource):
        """
        put (update) a resource

        :param str resource: resource path
        :return: the resource object
        :rtype: json
        """

        self._stayAlive()

        req = self.s.put(self.fullUrl(resource))
        return req.json()

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
            print('del request failed:',err)
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
            print('del request failed:',err)


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
            print('publish request failed:',err)



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

    def searchTerm(self, resource, search ,mode = 'default'):
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
        return req.json()



    def uploadFile(self, filename):
        """
        push (post) a file to the server

        :param Path filename: the file to be uploaded
        :return: the file object containing the related object selfUrl
        :rtype: APIObject
        """

        try:
            data = filename.open(mode = 'rb').read()
            ##workaround for file without file extensions
            if filename.suffix =='':
                filename = filename.with_suffix('.dcm')
            files  = { 'file' : (str(filename.name), data)}
        except:
            print ("opening file", filename, "failed, aborting")
            return

        res = self.s.post(self.url + 'upload', files = files)
        if res.status_code == requests.codes.created:
            obj = self.getAPIObjectType(res)
            obj.set(obj = res)
            return obj
        else:
            return res.status_code


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
                yield(chunk)

    def chunkFileUpload(self, fp, chunksize = 1024*4096):
        """
        upload large files in chunks of max 100 MB size

        :param Path fp: the file to upload
        :param int chunksize: size in bytes of the chunk parts, default is 4MB
        :return: the generated object
        :rtype: APIObject
        """
        parts = math.ceil(fp.stat().st_size/chunksize)
        part = 0
        err = False
        maxchunksize = 1024 * 1024 * 100
        if chunksize < maxchunksize:
            for chunk in self.chunkedread(fp, chunksize):
                part = part + 1
                print('uploading part {0} of {1}'.format(part,parts))

                files  = { 'file' : (str(fp.name), chunk)}
                res = self.s.post(self.url + 'chunked_upload?chunk={0}'.format(part), files = files)
                if res.status_code == requests.codes.ok:
                    print('uploaded part {0} of {1}'.format(part,parts))
                else:
                    err = True

            if not err:
                resource = 'chunked_upload/commit?filename={0}'.format(fp.name)
                res = self.postRequestSimple(resource)

                relObj = res['relatedObject']
                obj = self.getObject(relObj['selfUrl'])
                return obj

            else:
                return None
        else:
            print('not uploaded: defined chunksize {0} is bigger than the allowed maximum {1}'.format(chunksize, method))
            return None



    def getFile(self, resource):
        """
        return a APIFile object

        :param str resource: resource path
        :return: api file object  or status code
        :rtype: APIFile
        """
        if isinstance(resource, int):
            resource = 'files/{0}'.format(resource)

        res = self.getRequest(resource)

        if not isinstance(res, int):
            fObj = APIFile()
            fObj.set(res)
            return fObj
        else:
            return res



    def getObjectFiles(self, obj):
        """
        return a list of file objects contained in an object

        :param APIObject obj: object
        :return: list of APIFile
        :rtype: list of APIFile
        """
        filelist = list()

        fileurl = 'objects/{0}/files'.format(obj.id)

        fl = self.getAllPaginated(fileurl)

        for f in fl:
            res = self.getFile(f['selfUrl'])
            if not isinstance(res, int):
                filelist.append(res)
        return filelist

    def fileObjectVersion(self, data):
        """
        Extract VSDID and selfUrl of the related Object Version of the file after file upload

        :param json data: file object data
        :result: returns the id and the selfUrl of the Object Version
        :rtype: str
        """

        #data = json.loads(data)
        f = data['file']
        obj = data['relatedObject']
        fSelfUrl = f['selfUrl']
        return obj['selfUrl'], self.getOID(obj['selfUrl'])


    def getAllUnpublishedObjects(self, resource = 'objects/unpublished'):
        """ retrieve the unpublished objects as list of APIObject

        :param str resource: resource path (eg nextPageUrl) or default groups
        :param int rpp: results per page
        :param int page: page to display
        :return: list of objects
        :rtype: APIObjects
        """

        objects = list()
        res = self.getAllPaginated(resource)

        for item in res:
            obj = self.getObject(item.get('selfUrl'))
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




    def getFolderByName(self, search, mode = 'default'):
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


        self._stayAlive()

        res = self.s.get(url)

        if res.status_code == requests.codes.ok:

            result = list()
            res = res.json()

            for item in iter(res['items']):

                f = APIFolder()
                f.set(item)
                result.append(f)

            if len(result) == 1:

                folder = result[0]
                print('1 folder matching the search found')
                return folder

            else:

                print('list of {} folders matching the search found'.format(len(results)))
                return result
        else:

            return res.status_code

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
                basic = APIBasic()
                basic.set(obj = fold)
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
                basic = APIBasic()
                basic.set(obj = obj)
                o = self.getObject(basic.selfUrl)
                objlist.append(o)
            return objlist
        else:
            print('the folder does not have any contained objects')
            return None

    def deleteFolderContent(self, folder):
        """ delete all content from a folder (APIFolder)

        :param APIFolder folder: a folder object
        :return state: returns true if successful, else False
        :rtype: bool
        """

        state = False

        folder.containedObjects = None

        res = self.putRequest('folders', data = folder.get())

        if not isinstance(res, int):
            state = True

        return state

    def getFolderContent(self, folder, recursive = False, mode = 'd'):
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

        temp = dict([('folder', folder),('object', None)])

        if foldermode:
            content = list([temp])
        else:
            content = list()

        if objectmode:
            objects = self.getContainedObjects(folder)

            if objects is not None:
                for obj in objects:
                    temp = dict([('folder', folder),('object', obj)])
                    content.append(temp)

        if folders is not None:
            if recursive:
                for fold in folders:
                    content.extend(self.getFolderContent(fold, mode = mode, recursive = True))

            else:
                if foldermode:
                    for fold in folders:
                        temp = dict([('folder', folder),('object', None)])
                        content.append(temp)

        return content




    def searchOntologyTerm(self, search, oType = '0', mode = 'default'):
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
            url = self.url+"ontologies/{0}?$filter=Term%20eq%20%27{1}%27".format(oType,search)
        else:
            url = self.url+"ontologies/{0}?$filter=startswith(Term,%27{1}%27)%20eq%20true".format(oType,search)


        self._stayAlive()

        res = self.s.get(url)
        if res.status_code == requests.codes.ok:
            result = list()

            res = res.json()

            if len(res['items']) == 1:
                onto = APIOntology()
                onto.set(res['items'][0])
                print('1 ontology term matching the search found')
                return onto
            for item in iter(res['items']):
                onto = APIOntology()
                onto.set(item)
                result.append(onto)
            return result
        else:
            return res.status_code



    def getOntologyTermByID(self, oid, oType = 0):
        """
        Retrieve an ontology entry based on the IRI

        :param int oid: Identifier of the entry
        :param int oType: Resource type, available resources can be found using the OPTIONS on /api/ontologies). Default resouce is FMA (0)
        :return: ontology term entry
        :rtype: json
        """

        self._stayAlive()

        url = "ontologies/{0}/{1}".format(oType,oid)
        req = self.getRequest(url)
        return req.json()


    def getOntologyItem(self, resource, oType = 0):
        """
        Retrieve an ontology item object (APIOntology)

        :param int,str resource: resource path to the of the ontology item
        :param int oType: ontology type
        :return onto: the ontology item object
        :rtype: APIOntology
        """

        self._stayAlive()

        if isinstance(resource, int):
            resource = 'ontology/{0}/{1}'.format(resource, oType)

        res = self.getRequest(resource)

        if res:
            onto = APIOntology()
            onto.set(obj = res)

            return onto
        else:
            return None


    def getLicenseList(self):
        """ retrieve a list of the available licenses (APILicense)


        :return: list of available license objects
        :rtype: list of APILicense
        """

        res = self.getRequest('licenses')
        licenses = list()
        if res:
            for item in iter(res['items']):
                lic = APILicense()
                lic.set(obj = item)
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
            license = APILicense()
            license.set(obj = res)

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
                perm = APIObjectRight()
                perm.set(obj = item)
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
            perm = APIObjectRight()
            perm.set(obj = res)
            return perm
        else:
            return None

    def getGroups(self, resource = 'groups',  rpp = None, page = None):
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
        ppObj = APIPagination()
        ppObj.set(obj = res)

        for g in ppObj.items:
            group = APIGroup()
            group.set(obj = g)
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
            group = APIGroup()
            group.set(obj = res)
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
            user = APIUser()
            user.set(obj = res)
            return user
        else:
            return None

    def getPermissionSets(self, permset = 'default'):
        """
        get the Object Rights for a permission set

        :param str permset: name of the permission set: available are private, protect, default, collaborate, full or a list of permission ids (list)
        :return perms: list of object rights objects
        :rtype: APIObjectRight
        """

        if permset == 'private':
            lperms = list([1])
        elif permset == 'protect':
            lperms = list([2,3])
        elif permset == 'default':
            lperms = list([2,3,4])
        elif permset == 'collaborate':
            lperms = list([2,3,4,5])
        elif permset == 'full':
            lperms = list([2,3,4,5,6])
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
                right = APIObjectGroupRight()
                right.set(obj = res)
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
                right = APIObjectUserRight()
                right.set(obj = res)
                rights.append(right)

        return rights

    def postObjectRights(self, obj, group, perms, isuser = False):
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

        #creat the dict of rights
        rights = list()
        for perm in perms:
            rights.append(dict([('selfUrl', perm.selfUrl)]))

        if isuser:
            objRight = APIObjectUserRight()
            objRight.relatedObject = dict([('selfUrl', obj.selfUrl)])
            objRight.relatedRights = rights
            objRight.relatedUser = dict([('selfUrl', group.selfUrl)])
            res = self.postRequest('object-user-rights', data = objRight.get())
            objRight.set(res)

        else:
            objRight = APIObjectGroupRight()
            objRight.relatedObject = dict([('selfUrl', obj.selfUrl)])
            objRight.relatedRights = rights
            objRight.relatedGroup = dict([('selfUrl', group.selfUrl)])
            res = self.postRequest('object-group-rights', data = objRight.get())
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

        #creat the dict of rights
        rights = list()
        for perm in perms:
            rights.append(dict([('selfUrl', perm.selfUrl)]))

        objRight = APIObjectUserRight()
        objRight.relatedObject = dict([('selfUrl', obj.selfUrl)])
        objRight.relatedRights = rights
        objRight.relatedUser = dict([('selfUrl', user.selfUrl)])

        res = self.postRequest('object-user-rights', data = objRight.get())
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

        #creat the dict of rights
        rights = list()

        for perm in perms:
            rights.append(dict([('selfUrl', perm.selfUrl)]))

        objRight = APIObjectGroupRight()
        objRight.relatedObject = dict([('selfUrl', obj.selfUrl)])
        objRight.relatedRights = rights
        objRight.relatedGroup = dict([('selfUrl', group.selfUrl)])

        res = self.postRequest('object-group-rights', data = objRight.get())
        objRight.set(res)

        return objRight




    def getModalityList(self):
        """
        retrieve a list of modalities objects (APIModality)

        :return: list of available modalities
        :rtype: list of APIModality
        """

        modalities = list()
        items = self.getAllPaginated('modalities', itemlist = list())
        if items:
            for item in items:
                modality = APIModality()
                modality.set(obj = item)
                modalities.append(modality)
        return modalities

    def getModality(self, resource):
        """ retrieve a modalities object (APIModality)


        :param int,str resource: resource path to the of the modality
        :return: the modality object
        :rtype: APIModality
        """

        if isinstance(resource, int):
            resource = 'modalities/{0}'.format(resource)

        res = self.getRequest(resource)
        if res:
            mod = APIModality()
            mod.set(obj = res)

            return mod
        else:
            return None

    def readFolders(self,folderList):
    #first pass: create one entry for each folder:
        folderHash={}
        for folder in folderList['items']:
            ID=folder['id']
            folderHash[ID]=Folder()
            folderHash[ID].ID=ID
            folderHash[ID].name=folder['name']
            folderHash[ID].childFolders=[]

    #second pass: create references to parent and child folders
        for folder in folderList['items']:
            ID=folder['id']
            if (folder['childFolders']!=None):
            #print (folder['childFolders'],ID)
                for child in folder['childFolders']:
                    childID=int(child['selfUrl'].split("/")[-1])
                    if (folderHash.has_key(childID)):
                        folderHash[ID].childFolders.append(folderHash[childID])
            if (folder['parentFolder']!=None):
                parentID=int(folder['parentFolder']['selfUrl'].split("/")[-1])
                if (folderHash.has_key(parentID)):
                    folderHash[ID].parentFolder=folderHash[parentID]
            if (not folder['containedObjects']==None):
                folderHash[ID].containedObjects={}
                for obj in folder['containedObjects']:
                    objID=obj['selfUrl'].split("/")[-1]
                    folderHash[ID].containedObjects[objID]=obj['selfUrl']

        #third pass: gett full path names in folder hierarchy
        for key, folder in folderHash.iteritems():
            folder.getFullName()

        return folderHash


    def addLink(self, obj1, obj2):
        """ add an object link

        :param APIBasic obj1: a linked object with selfUrl
        :param APIBasic obj2: a linked object with selfUrl
        :return: the created object-link
        :rtype: json
        """

        link = APIObjectLink()
        link.object1 = dict([('selfUrl', obj1.selfUrl)])
        link.object2 = dict([('selfUrl', obj2.selfUrl)])

        return  self.postRequest('object-links', data = link.get())

    def addOntologyToObject(self, obj, ontology, pos = 0):
        """ add an ontoly term to an object

        :param APIBasic obj: basic object
        :param APIOntology ontology: ontology object
        :param int pos: position of the ontology term, default = 1
        :return: returns true if successfully added
        :rtype: bool
        """

        isset = False
        if isinstance(pos, int):
                onto = APIObjectOntology()
                onto.position = pos
                onto.object = dict([('selfUrl', obj.selfUrl)])
                onto.ontologyItem = dict([('selfUrl', ontology.selfUrl)])
                onto.type = ontology.type

                res = self.postRequest('object-ontologies/{0}'.format(ontology.type), data = onto.get())
                if res:
                    isset = True
        else:
            print('position needs to be a number (int)')

        return isset

    def postFolder(self, parent, name, check = True):
        """
        creates the folder with a given name (name) inside a folder (parent) if not already exists

        :param APIFolder parent: the root folder
        :param str name: name of the folder which should be created
        :param bool check: it we should check if already exist, default = True
        :return: the folder object of the generated folder or the existing folder
        :rtype: APIFolder
        """

        folder = APIFolder()
        folder.parentFolder = dict([('selfUrl', parent.selfUrl)])
        folder.name = name

        exists = False

        if check:
            if parent.childFolders:
                for child in parent.childFolders:
                    basic = APIBasic()
                    basic.set(obj = child)
                    fold = self.getFolder(basic.selfUrl)
                    if fold is not None:
                        if fold.name == name:
                            print('folder {0} already exists, id: {1}'.format(name, fold.id))
                            exists = True
                    else:
                        print('unexpected error, folder exists but cannot be retrieved')
                        exists = True

        if not exists:
            res = self.postRequest('folders', data = folder.get())
            if res is not None:
                folder.set(obj = res)
                print('folder {0} created, has id {1}'.format(name, folder.id))
            return folder
        else:
            return fold

    def deleteFolder(self, folder, recursive = False):
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
                return self.deleteFolder(f, recursive = recursive)
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

        for i in range (parents, len(folders)):
            folders.remove(folders[i])

        folders.reverse()
        fparent = rootfolder

        if fparent:
            for fname in folders:
                fchild = None
                if fparent:
                    if fparent.childFolders:
                        for child in fparent.childFolders:
                            fold = self.getFolder(child['selfUrl'])
                            if fold.name == fname:
                                fchild = APIFolder()
                                #fchild.set(obj = fold.get())
                                fchild = fold
                if not fchild:
                    f = APIFolder()
                    f.name = fname
                    f.parentFolder = dict([('selfUrl',fparent.selfUrl)])
                   # f.toJson()
                    res = self.postRequest('folders', f.get())
                    fparent.set(obj = res)

                else:
                    fparent = fchild

            return fparent
        else:
            print('Root folder does not exist', rootfolder)
            #jData = jFolder(folder)
            return None



    def addObjectToFolder(self, target, obj):
        """
        add an object to the folder

        :param APIFolder target: the target folder
        :param APIObject obj: the object to copy
        :return: updated folder
        :rtype: APIFolder
        """

        objSelfUrl = dict([('selfUrl',obj.selfUrl)])
        objects = target.containedObjects

        if not objects:
            objects = list()
        if objects.count(objSelfUrl) == 0:
            objects.append(objSelfUrl)
            target.containedObjects = objects
            res = self.putRequest('folders', data = target.get())

            if not isinstance(res, int):
                target = APIFolder()
                target.set(obj = res)
                return target
            else:
                return res
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

        objSelfUrl = dict([('selfUrl',obj.selfUrl)])
        objects = target.containedObjects

        isset = False

        if objects:
            if objects.count(objSelfUrl) > 0 :
                objects.remove(objSelfUrl)
                target.containedObjects = objects
                res = self.putRequest('folders', data = target.get())

                if not isinstance(res, int):
                    isset = True
            else:
                print('object not part of that folder')
        else:
            print('folder containes no objects')

        return isset

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
            basic = APIBasic()
            basic.set(obj = obj.modality)
            mod = self.getModality(basic.selfUrl)

            print('name: ', mod.name)
            print('description', mod.description)
            print('selfUrl: ', mod.selfUrl)
            print('id: ', mod.id)



        if obj.ontologyItems is not None:
            print('---------Ontology items----------')
            for onto in obj.ontologyItems:
                basic = APIBasic()
                basic.set(obj = onto)
                ontology = self.getOntologyItem(basic.selfUrl)

                print('Term: ', ontology.term)
                print('type', ontology.type)
                print('selfUrl: ', ontology.selfUrl)
                print('id: ', ontology.id)

        if obj.license is not None:
            print('---------License----------')
            basic = APIBasic()
            basic.set(obj = obj.license)
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
                print(user.get())
                print('rights:')
                for r in u.relatedRights:
                    print(self.getObjectRight(r['selfUrl']).get())
        else:
            print('nothing here')

        print('---------GroupRights----------')
        gr = self.getObjectGroupRights(obj)
        if gr:
            for g in gr:
                group = self.getGroup(g.relatedGroup['selfUrl'])
                print('group:')
                print(group.get())
                print('rights:')
                for r in g.relatedRights:
                    print(self.getObjectRight(r['selfUrl']).get())
        else:
            print('nothing here')


class APIBasic(object):
    """
    APIBasic

    :attributes:
        * selfUrl
    """

    oKeys = list([
       'selfUrl'
        ])

    def __init__(self, oKeys = oKeys):
        for v in oKeys:
                setattr(self, v, None)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIBasic obj: A APIBasic object
        """
        if  obj:
            for v in self.oKeys:
                if v in obj:
                    setattr(self, v, obj[v])
        else:
            for v in self.oKeys:
                setattr(self, v, None)

    def get(self):
        """transforms the class object into a json readable dict"""
        return self.__dict__

    def show(self):
        """prints the json to the console, nicely printed"""
        print(json.dumps(self.__dict__, sort_keys = True, indent = '    '))

class APIObject(APIBasic):
    """
    API Object

    :attributes:
        * selfUrl
        * id
        * name
        * type
        * description
        * objectGroupRights
        * objectUserRights
        * objectPreviews
        * createdDate
        * ontologyItems
        * ontologyItemRelations
        * ontologyCount
        * license
        * files
        * linkedObjects
        * linkedObjectRelations
        * downloadUrl
    """

    oKeys = list([
        'id',
        'name',
        'type',
        'description',
        'objectGroupRights',
        'objectUserRights',
        'objectPreviews',
        'createdDate',
        'ontologyItems',
        'ontologyItemRelations',
        'ontologyCount',
        'license',
        'files',
        'linkedObjects',
        'linkedObjectRelations',
        'downloadUrl'
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self, ):
        super(APIObject, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObject obj: A APIObject object
        """
        super(APIObject, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObject, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObject, self).show()

    def download(self, apisession, wp):
        """
        download the object into a ZIP file based on the object name and the working directory

        :param VSDConnecter apisession: authenticated api session
        :param Path wp: workpath, where to store the zip
        :return: None or filename
        :rtype: str
        """

        fp = Path(self.name).with_suffix('.zip')
        
        if wp:
            fp = Path(wp, fp)

        res = apisession.s.get(self.downloadUrl, stream = True)
        if res.ok:
            with fp.open('wb') as f:
                shutil.copyfileobj(res.raw, f)
            return fp
        else:
            return None

    def getType(self):
        """return the type APIObjectType object of the class"""

        otype = APIObjectType()
        otype.set(obj = self.type)
        
        return otype

    def getLicense(self):
        """ return the license APILicence object"""

        license = APILicense()
        license.set(obj = self.license)

        return license

    def getUserRights(self, apisession):
        """ return a list of object user rights objects

        :param VSDConnecter apisession: authenticated api session to SMIR
        :return: list of object userrights
        :rtype: APIObjectUserRights
        """
        
        rights = None

        if self.objectUserRights:
            rights = list()
            for item in self.objectUserRights:
                right = APIBasic()
                right.set(obj = item)
                res = apisession.getRequest(right.selfUrl)
                uright = APIObjectUserRight()
                uright.set(obj = res)
                rights.append(uright)

        return rights

    def getGroupRights(self, apisession):
        """return a list of group Rights objects 

        :param VSDConnecter apisession: authenticated api session to SMIR
        :return: list of object grouprights
        :rtype: APIObjectGroupRights
        """
        
        rights = None

        if self.objectGroupRights:
            rights = list()
            for item in self.objectGroupRights:
                right = APIBasic()
                right.set(obj = item)
                res = apisession.getRequest(right.selfUrl)
                gright = APIObjectGroupRight()
                gright.set(obj = res)
                rights.append(gright)

        return rights             

    def previews(self):

        print('todo')

class APIObjectRaw(APIObject):
    """
    APIObjectRaw (Serie, Raw Images)

     :attributes:
        * selfUrl
        * id
        * name
        * type
        * description
        * objectGroupRights
        * objectUserRights
        * objectPreviews
        * createdDate
        * ontologyItems
        * ontologyItemRelations
        * ontologyCount
        * license
        * files
        * linkedObjects
        * linkedObjectRelations
        * downloadUrl
        * rawImage
        * sliceThickness
        * spaceBetweenSlices
        * kilovoltPeak
        * modality
    """
    oKeys = list([
        'rawImage'
        ])

    for __i in APIObject.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys)

    def set(self, obj = None):
        """ sets class variable for each key in the object to the keyname and its value

        :param APIObjectRaw obj: a APIObjectRaw object
        """
        super(APIObject, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObject, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObject, self).show()

    def download(self, apisession, wp):
        """ download the object as zip to a directory"""
        return APIObject.download(self, apisession, wp)

    def getType(self):
        """return the type APIObjectType object of the class"""
        return APIObject.getType(self)

    def getLicense(self):
        """ return the license APILicence object"""
        return APIObject.getLicense(self)

    def getMeta(self):
        """return the meta infos of the object as object APIRawImage """

        meta = APIRawImage()
        meta.set(obj = self.rawImage)

        return meta

    def getUserRights(self, apisession):
        """ return the user rights object """
        return APIObject.getUserRights(self, apisession)

    def getGroupRights(self, apisession):
        """ return the group rights object """
        return APIObject.getGroupRights(self, apisession)

    def getModality(self):
        """ get the modality of an object 

        :return: the modality object
        :rtype: APIModality
        """
        mod = APIModality()
        mod.set(obj = self.getMeta().modality)

        return mod


class APIObjectSeg(APIObject):
    """
    APIObjectSeg (Segmentation objects)

    :attributes:
        * selfUrl
        * id
        * name
        * type
        * description
        * objectGroupRights
        * objectUserRights
        * objectPreviews
        * createdDate
        * ontologyItems
        * ontologyItemRelations
        * ontologyCount
        * license
        * files
        * linkedObjects
        * linkedObjectRelations
        * downloadUrl
        * segmentationImage
        * SegmentationMethod
        * SegmentationMethodDescription

    """
    oKeys = list([
        'segmentationImage'
        ])


    for __i in APIObject.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectSeg obj: A APIObjectSeg object
        """
        super(APIObject, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObject, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObject, self).show()

    def download(self, apisession, wp):
        """ download the object as zip to a directory"""
        return APIObject.download(self, apisession, wp)

    def getType(self):
        """return the type APIObjectType object of the class"""
        return APIObject.getType(self)

    def getLicense(self):
        """ return the license APILicence object"""
        return APIObject.getLicense(self)

    def getMeta(self):
        """return the meta infos of the object as object APIRawImage """

        meta = APISegImage()
        meta.set(obj = self.segmentationImage)

        return meta

    def getUserRights(self, apisession):
        """ return the user rights object """
        return APIObject.getUserRights(self, apisession)

    def getGroupRights(self, apisession):
        """ return the group rights object """
        return APIObject.getGroupRights(self, apisession)


class APIObjectSm(APIObject):
    """
    APIObjectSm (Statistical Models)

    :attributes:
        * selfUrl
        * id
        * name
        * type
        * description
        * objectGroupRights
        * objectUserRights
        * objectPreviews
        * createdDate
        * ontologyItems
        * ontologyItemRelations
        * ontologyCount
        * license
        * files
        * linkedObjects
        * linkedObjectRelations
        * downloadUrl
        * modality
    """

    oKeys = list()

    for __i in APIObject.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectSm obj: A APIObjectSm object
        """
        super(APIObject, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObject, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObject, self).show()

    def download(self, apisession, wp):
        """ download the object as zip to a directory"""
        return APIObject.download(self, apisession, wp)

    def getType(self):
        """return the type APIObjectType object of the class"""
        return APIObject.getType(self)

    def getLicense(self):
        """ return the license APILicence object"""
        return APIObject.getLicense(self)

    def getMeta(self):
        """return the meta infos of the object as object APIRawImage """

        meta = APISurfaceModel()
        meta.set(obj = self.surfaceModel)

        return meta

    def getUserRights(self, apisession):
        """ return the user rights object """
        return APIObject.getUserRights(self, apisession)

    def getGroupRights(self, apisession):
        """ return the group rights object """
        return APIObject.getGroupRights(self, apisession)

class APIObjectCtDef(APIObject):
    """
    APIObjectCtDef (Clinical Trial Definition)

    :attributes:
        * selfUrl
        * id
        * name
        * type
        * description
        * objectGroupRights
        * objectUserRights
        * objectPreviews
        * createdDate
        * modality
        * ontologyItems
        * ontologyItemRelations
        * ontologyCount
        * license
        * files
        * linkedObjects
        * linkedObjectRelations
        * downloadUrl
        * clinicalStudyDefinition
    """

    oKeys = list([
        'clinicalStudyDefinition'
    ])

    for __i in APIObject.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectCtDef obj: A APIObjectCtDef object
        """
        super(APIObject, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObject, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObject, self).show()

    def download(self, apisession, wp):
        """ download the object as zip to a directory"""
        return APIObject.download(self, apisession, wp)

    def getType(self):
        """return the type APIObjectType object of the class"""
        return APIObject.getType(self)

    def getLicense(self):
        """ return the license APILicence object"""
        return APIObject.getLicense(self)

    def getMeta(self):
        """return the meta infos of the object as object APIRawImage """

        meta = APICtDef()
        meta.set(obj = self.clinicalStudyDefinition)

        return meta

    def getUserRights(self, apisession):
        """ return the user rights object """
        return APIObject.getUserRights(self, apisession)

    def getGroupRights(self, apisession):
        """ return the group rights object """
        return APIObject.getGroupRights(self, apisession)

class APIObjectCtData(APIObject):
    """
    APIObjectCtData (Clinical Trial Data)


    :attributes:
        * selfUrl
        * id
        * name
        * type
        * description
        * objectGroupRights
        * objectUserRights
        * objectPreviews
        * createdDate
        * modality
        * ontologyItems
        * ontologyItemRelations
        * ontologyCount
        * license
        * files
        * linkedObjects
        * linkedObjectRelations
        * downloadUrl
        * clinicalStudyDefinition
        * subject

    """
    oKeys = list([
        'clinicalStudyDefinition',
        'subject'
    ])

    for __i in APIObject.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectCtData obj: A APIObjectCtData object
        """
        super(APIObject, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObject, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObject, self).show()


class APIObjectSurfModel(APIObject):
    """
    APIObjectSurfModel (Surface Model)


    :attributes:
        * selfUrl
        * id
        * name
        * type
        * description
        * objectGroupRights
        * objectUserRights
        * objectPreviews
        * createdDate
        * modality
        * ontologyItems
        * ontologyItemRelations
        * ontologyCount
        * license
        * files
        * linkedObjects
        * linkedObjectRelations
        * downloadUrl
        * tbd

    """
    oKeys = list([
        'Facet',
        'Vertex'
        ])


    for __i in APIObject.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectSurfModel obj: A APIObjectSurfModel object
        """
        super(APIObject, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObject, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObject, self).show()


class APIObjectStudy(APIObject):
    """
    APIObjectStudy (Study)


    :attributes:
        * selfUrl
        * id
        * name
        * type
        * description
        * objectGroupRights
        * objectUserRights
        * objectPreviews
        * createdDate
        * modality
        * ontologyItems
        * ontologyItemRelations
        * ontologyCount
        * license
        * files
        * linkedObjects
        * linkedObjectRelations
        * downloadUrl

    """
    oKeys = list()


    for __i in APIObject.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectStudy obj: A APIObjectStudy object
        """
        super(APIObject, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObject, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObject, self).show()


class APIObjectSubject(APIObject):
    """
    APIObjectSubject (Subject)


    :attributes:
        * selfUrl
        * id
        * name
        * type
        * description
        * objectGroupRights
        * objectUserRights
        * objectPreviews
        * createdDate
        * modality
        * ontologyItems
        * ontologyItemRelations
        * ontologyCount
        * license
        * files
        * linkedObjects
        * linkedObjectRelations
        * downloadUrl
        * subject

    """
    oKeys = list([
        'subject'
        ])


    for __i in APIObject.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectSubject obj: A APIObjectSubject object
        """
        super(APIObject, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObject, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObject, self).show()



class APIObjectGenPlatform(APIObject):
    """
    APIObjectGenPlatform (Genomic Platform)


    :attributes:
        * selfUrl
        * id
        * name
        * type
        * description
        * objectGroupRights
        * objectUserRights
        * objectPreviews
        * createdDate
        * modality
        * ontologyItems
        * ontologyItemRelations
        * ontologyCount
        * license
        * files
        * linkedObjects
        * linkedObjectRelations
        * downloadUrl

    """
    oKeys = list()


    for __i in APIObject.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectGenPlatform obj: A APIObjectGenPlatform object
        """
        super(APIObject, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObject, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObject, self).show()



class APIObjectGenSample(APIObject):
    """
    APIObjectGenSample (Genomic sample)


    :attributes:
        * selfUrl
        * id
        * name
        * type
        * description
        * objectGroupRights
        * objectUserRights
        * objectPreviews
        * createdDate
        * modality
        * ontologyItems
        * ontologyItemRelations
        * ontologyCount
        * license
        * files
        * linkedObjects
        * linkedObjectRelations
        * downloadUrl

    """
    oKeys = list()


    for __i in APIObject.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectGenSample obj: A APIObjectGenSample object
        """
        super(APIObject, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObject, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObject, self).show()


class APIObjectGenSeries(APIObject):
    """
    APIObjectGenSeries (Genomic series)


    :attributes:
        * selfUrl
        * id
        * name
        * type
        * description
        * objectGroupRights
        * objectUserRights
        * objectPreviews
        * createdDate
        * modality
        * ontologyItems
        * ontologyItemRelations
        * ontologyCount
        * license
        * files
        * linkedObjects
        * linkedObjectRelations
        * downloadUrl

    """
    oKeys = list()


    for __i in APIObject.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectGenSeries obj: A APIObjectGenSeries object
        """
        super(APIObject, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObject, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObject, self).show()



class APIFolder(APIBasic):
    """
    Folder API Object

    :attributes:
        * selfUrl
        * id
        * name
        * level
        * parentFolder
        * childFolders
        * folderGroupRights
        * folderUserRights
        * containedObjects
    """
    oKeys = list([
        'id',
        'name',
        'level',
        'parentFolder',
        'childFolders',
        'folderGroupRights',
        'folderUserRights',
        'containedObjects'
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIFolder, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIFolder obj: A APIFolder object
        """
        super(APIFolder, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIFolder, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIFolder, self).show()

class APIOntology(APIBasic):
    """
    API class for ontology entries

    :attributes:
        * selfUrl
        * id
        * term
        * type

    """
    oKeys = list([
        'id',
        'term',
        'type',
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIOntology, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIOntology obj: A APIOntology object
        """
        super(APIOntology, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIOntology, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIOntology, self).show()

class APIObjectOntology(APIBasic):
    """
    API class for object-ontology entries


    :attributes:
        * selfUrl
        * id
        * type
        * object
        * ontologyItem
        * position

    """
    oKeys = list([
        'id',
        'type',
        'object',
        'ontologyItem',
        'position'
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObjectOntology, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectOntology obj: A APIObjectOntology object
        """
        super(APIObjectOntology, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObjectOntology, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObjectOntology, self).show()

class APIFile(APIBasic):
    """
    API class for files

    :attributes:
        * selfUrl
        * id
        * createdDate
        * downloadUrl
        * originalFileName
        * anonymizedFileHashCode
        * size
        * fileHashCode

    """
    oKeys = list([
        'id',
        'createdDate',
        'downloadUrl',
        'originalFileName',
        'anonymizedFileHashCode',
        'size',
        'fileHashCode'
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIFile, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIFile obj: A APIFile object
        """
        super(APIFile, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIFile, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIFile, self).show()

class APILicense(APIBasic):
    """
    API class for licenses

    :attributes:
        * selfUrl
        * id
        * name
        * description

    """
    oKeys = list([
        'id',
        'description',
        'name',
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APILicense, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APILicense obj: A APILicense object
        """
        super(APILicense, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APILicense, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APILicense, self).show()

class APIObjectRight(APIBasic):
    """
    API class for object rights

    :attributes:
        * selfUrl
        * id
        * name
        * description

    """
    oKeys = list([
        'id',
        'description',
        'name',
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObjectRight, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectRight obj: A APIObjectRight object
        """
        super(APIObjectRight, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObjectRight, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObjectRight, self).show()

class APIObjectLink(APIBasic):
    """
    API class for object links

    :attributes:
        * selfUrl
        * id
        * description
        * object1
        * object2

    """
    oKeys = list([
        'id',
        'description',
        'object1',
        'object2',
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObjectLink, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectLink obj: A APIObjectLink object
        """
        super(APIObjectLink, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObjectLink, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObjectLink, self).show()

class APIModality(APIBasic):
    """
    API class for modalities

    :attributes:
        * selfUrl
        * id
        * name
        * description

    """
    oKeys = list([
        'id',
        'description',
        'name'
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIModality, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIModality obj: A APIModality object
        """
        super(APIModality, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIModality, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIModality, self).show()

class APIObjectGroupRight(APIBasic):
    """
    API class for object group rights

    :attributes:
        * selfUrl
        * id
        * relatedObject
        * relatedRights
        * relatedGroup

    """
    oKeys = list([
        'id',
        'relatedObject',
        'relatedRights',
        'relatedGroup'
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObjectGroupRight, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectGroupRight obj: A APIObjectGroupRight object
        """
        super(APIObjectGroupRight, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObjectGroupRight, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObjectGroupRight, self).show()

class APIObjectUserRight(APIBasic):
    """
    API class for object user rights


    :attributes:
        * selfUrl
        * id
        * relatedObject
        * relatedRights
        * relatedUser

    """
    oKeys = list([
        'id',
        'relatedObject',
        'relatedRights',
        'relatedUser'
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIObjectUserRight, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectUserRight obj: A APIObjectUserRight object
        """
        super(APIObjectUserRight, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIObjectUserRight, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIObjectUserRight, self).show()

class APIGroup(APIBasic):
    """
    API class for groups


    :attributes:
        * selfUrl
        * id
        * Chief
        * name

    """
    oKeys = list([
        'id',
        'Chief',
        'name'
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIGroup, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIGroup obj: A APIGroup object
        """
        super(APIGroup, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIGroup, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIGroup, self).show()

class APIUser(APIBasic):
    """
    API class for users

    :attributes:
        * selfUrl
        * id
        * username

    """
    oKeys = list([
        'id',
        'username'
        ])

    for __i in APIBasic.oKeys:
        oKeys.append(__i)

    def __init__(self):
        super(APIUser, self).__init__(self.oKeys)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIUser obj: A APIUser object
        """
        super(APIUser, self).set(obj = obj)

    def get(self):
        """transforms the class object into a json readable dict"""
        return super(APIUser, self).get()

    def show(self):
        """prints the json to the console, nicely printed"""
        super(APIUser, self).show()



class APIPagination(object):
    """
    API class for Pagination results


    :attributes:
        * totalCount
        * pagination
        * items
        * nextPageUrl

    """
    oKeys = list([
        'totalCount',
        'pagination',
        'items',
        'nextPageUrl'
        ])

    def __init__(self, oKeys = oKeys):
        for v in oKeys:
                setattr(self, v, None)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIPagination obj: A APIPagination object
        """
        if  obj:
            for v in self.oKeys:
                if v in obj:
                    setattr(self, v, obj[v])
        else:
            for v in self.oKeys:
                setattr(self, v, None)

    def get(self):
        """transforms the class object into a json readable dict"""
        return self.__dict__

    def show(self):
        """prints the json to the console, nicely printed"""
        print(json.dumps(self.__dict__, sort_keys = True, indent = '    '))

    def items(self, otype = Plain):
        """ return the items as list of correct APIObjects objects
        
        :param str otpye: the type of object to return
        :returns: list of API objects
        :rtpye: list

        :available object types:
        * RawImage
        * SegementationImage
        * ClinicalStudyData
        * ClinicalStudyDefinition
        * GenomicPlatform
        * GenomicSample
        * GenomicSeries
        * Plain
        * PlainSubject
        * StatisticalModel
        * Study
        * Subject
        * SurfaceModel
        * 
        """

        for item in self.items:
            if otype == 'RawImage':
            obj = APIObjectRaw()
        elif otype == 'SegmentationImage':
            obj = APIObjectSeg()
        elif otype == 'StatisticalModel':
            obj = APIObjectSm()
        elif otype == 'ClinicalStudyDefinition':
            obj = APIObjectCtDef()
        elif otype == 'ClinicalStudyData':
            obj = APIObjectCtData()
        elif otype == 'SurfaceModel':
            obj = APIObjectSurfModel()
        elif otype == 'GenomicPlatform':
            obj = APIObjectGenPlatform()
        elif otype == 'GenomicSample':
            obj = APIObjectGenSample()
        elif otype == 'GenomicSeries':
            obj = APIObjectGenSeries()
        elif otype == 'Study':
            obj = APIObjectStudy()
        elif otype == 'Subject':
            obj = APIObjectSubject()
        elif otype == 'Plain':
            obj = APIObject()
        elif otype == 'PlainSubject':
            obj = APIObject()
        else:
            obj = APIObject()
        return obj

    def getPage(self, apisession, resource):
        """return the result for a specific page nr 

        :param VSDConnecter apisession: the authenticate api session
        :param str resource: page to return as selfUrl
        :return: list of items
        :rtype: list()
        """

        res = apisession.getRequest(resource)

        if res:
            print('todo')

    def all(self, apisession, itemlist = list()):
        """
        returns all items as list

        :param VSDConnecter apisession: the authenticate api session
        :param list itemlist: list of items
        :return: list of all items
        :rtype: list 
        """

        for item in self.items:
            itemlist.append(item)
        
        if  self.nextPageUrl:

                return self.all(self.nextPageUrl, itemlist = itemlist)
            else:
                return itemlist
        else:
            return itemlist
        
##
## View Models
##

class APIObjectType(object):
    """
    API class for object type view model

    :attributes:
        * name
        * displayName
        * displayNameShort
        * selfUrl

    """
    oKeys = list([
        'name',
        'displayName',
        'displayNameShort',
        'selfUrl'
        ])

    def __init__(self, oKeys = oKeys):
        for v in oKeys:
                setattr(self, v, None)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIObjectType obj: A APIObjectType object
        """
        if  obj:
            for v in self.oKeys:
                if v in obj:
                    setattr(self, v, obj[v])
        else:
            for v in self.oKeys:
                setattr(self, v, None)

    def get(self):
        """transforms the class object into a json readable dict"""
        return self.__dict__

    def show(self):
        """prints the json to the console, nicely printed"""
        print(json.dumps(self.__dict__, sort_keys = True, indent = '    '))



class APIRawImage(object):
    """
    API class for Raw Image view model


    :attributes:
        * sliceThickness
        * spaceBetweenSlices
        * kilovoltPeak
        * modality

    """
    oKeys = list([
        'sliceThickness',
        'spaceBetweenSlices',
        'kilovoltPeak',
        'modality'
        ])

    def __init__(self, oKeys = oKeys):
        for v in oKeys:
                setattr(self, v, None)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIRawImage obj: A APIRawImage object
        """
        if  obj:
            for v in self.oKeys:
                if v in obj:
                    setattr(self, v, obj[v])
        else:
            for v in self.oKeys:
                setattr(self, v, None)

    def get(self):
        """transforms the class object into a json readable dict"""
        return self.__dict__

    def show(self):
        """prints the json to the console, nicely printed"""
        print(json.dumps(self.__dict__, sort_keys = True, indent = '    '))



class APISegImage(object):
    """
    API class for segmenation image view model


    :attributes:
        * methodDescription
        * segmentationMethod

    """
    oKeys = list([
        'methodDescription',
        'segmentationMethod'
        ])

    def __init__(self, oKeys = oKeys):
        for v in oKeys:
                setattr(self, v, None)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APISegImage obj: A APISegImage object
        """
        if  obj:
            for v in self.oKeys:
                if v in obj:
                    setattr(self, v, obj[v])
        else:
            for v in self.oKeys:
                setattr(self, v, None)

    def get(self):
        """transforms the class object into a json readable dict"""
        return self.__dict__

    def show(self):
        """prints the json to the console, nicely printed"""
        print(json.dumps(self.__dict__, sort_keys = True, indent = '    '))


# #class APIStatisticalModel(object):
    """
    API class for Statistical model view model - empty
    """

## class APIStudyModel(object):
    """
    API class for Statistical model view model - empty
    """



class APISubject(object):
    """
    API class for Subject view model

    :attributes:
        * subjectKey

    """
    oKeys = list([
        'subjectKey'
        ])

    def __init__(self, oKeys = oKeys):
        for v in oKeys:
                setattr(self, v, None)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APISubject obj: A APISubject object
        """
        if  obj:
            for v in self.oKeys:
                if v in obj:
                    setattr(self, v, obj[v])
        else:
            for v in self.oKeys:
                setattr(self, v, None)

    def get(self):
        """transforms the class object into a json readable dict"""
        return self.__dict__

    def show(self):
        """prints the json to the console, nicely printed"""
        print(json.dumps(self.__dict__, sort_keys = True, indent = '    '))


## class APICtData(object):
    """
    API class for clinical trial data view model  - empty
    """

class APICtDef(object):
    """
    API class for clinical trail definition view model

    :attributes:
    * studyOID
    * studyName
    * studyDescription
    * protocolName
    * metaDataVersionOID
    * metaDataVersionName

    """

    oKeys = list([
        'studyOID',
        'studyName',
        'studyDescription',
        'protocolName',
        'metaDataVersionOID',
        'metaDataVersionName'
        ])

    def __init__(self, oKeys = oKeys):
        for v in oKeys:
                setattr(self, v, None)

    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APICtDef obj: A APICtDef object
        """
        if  obj:
            for v in self.oKeys:
                if v in obj:
                    setattr(self, v, obj[v])
        else:
            for v in self.oKeys:
                setattr(self, v, None)

    def get(self):
        """transforms the class object into a json readable dict"""
        return self.__dict__

    def show(self):
        """prints the json to the console, nicely printed"""
        print(json.dumps(self.__dict__, sort_keys = True, indent = '    '))


class APIGenPlatform(object):
    """
    API class for  genomic platform view model
    """

class APIGenSeries(object):
    """
    API class for genomic series view model
    """

class APIGenSample(object):
    """
    API class for genomic sample view model
    """

class APIPlain(object):
    """
    API class for plain (undefined object) model view model
    """

class APIPlainSubject(object):
    """
    API class for plain subject (undefined subject object) model view model
    """




class APIToken(object):
    """
    API class to work with the tokens

    :attributes:
        * tokenType
        * tokenValue

    """
    oKeys = list([
        'tokenType',
        'tokenValue'
        ])

    def __init__(self, oKeys = oKeys):
        for v in oKeys:
                setattr(self, v, None)


    def set(self, obj = None):
        """
        sets class variable for each key in the object to the keyname and its value

        :param APIToken obj: A APIToken object
        """
        if  obj:
            for v in self.oKeys:
                if v in obj:
                    setattr(self, v, obj[v])
        else:
            for v in self.oKeys:
                setattr(self, v, None)

    def get(self):
        """transforms the class object into a json readable dict"""
        return self.__dict__

    def show(self):
        """prints the json to the console, nicely printed"""
        print(json.dumps(self.__dict__, sort_keys = True, indent = '    '))
    
