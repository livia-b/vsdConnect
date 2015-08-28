#!/usr/bin/python

# connectVSD 0.2
# (c) Tobias Gass, 2015
# conncetVSD 0.2 python 3 @Michael Kistler 2015
# changed / added auth 
from __future__ import print_function

import sys
import math

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
    from urllib.parse import quote
else:
    from urlparse import urlparse
    from urllib import quote
import json
import getpass
from pathlib import Path, PurePath, WindowsPath
import requests
import logging
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

def statusDescription(res):
    """
    Simple wrapping around status_codes dictionary

    :param res: status code
    :type res: int
    :return: status description
    :rtype: str
    """
    if isinstance(res,int):
        return requests.status_codes._codes[res][0]


class SAMLAuth(AuthBase):
    """Attaches SMAL to the given Request object. extends the request package auth class"""
    def __init__(self, enctoken):
        self.enctoken = enctoken

    def __call__(self, r):
        # modify and return the request
        r.headers['Authorization'] = b'SAML auth=' + self.enctoken
        return r

def samltoken(fp, stsurl = 'https://ciam-dev-chic.custodix.com/sts/services/STS'):
    ''' 
    generates the saml auth token from a credentials file 

    :param fp: (Path) file with the credentials (xml file)
    :param stsurl: (str) url to the STS authority
    :returns: (byte) enctoken 
    '''

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
    APIURL='https://demo.virtualskeleton.ch/api/'

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
            logging.debug("authtype basic")
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
        '''
        check the response of a request call to the resouce. 
        '''
        
        try:
            response.raise_for_status()
            return True, response.status_code

        except requests.exceptions.HTTPError as e:
            print("And you get an HTTPError: {0}".format(e))
            return False, response.status_code

    def _validate_exp(self):
        '''
        checks if the session is still valid
        '''
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
        '''
        checks if the token has expired, if yes, request a new token and initiates a new session

        '''
        if not self._validate_exp():
            self.s.auth = JWTAuth(self.getJWTtoken().tokenValue)

 
    def getJWTtoken(self):
        '''
        request the JWT token from the server using Basic Auth

        :returns token: a authentication token (APIToken) or None
        '''

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
        '''create an APIObject depending on the type 

        :param response: (json) object data
        :returns: (APIObject) object
        '''
        apiObject = APIObject()
        apiObject.set(obj = response)
        if apiObject.type == 1:
            obj = APIObjectRaw()
        elif apiObject.type == 2:
            obj = APIObjectSeg()
        elif apiObject.type == 3:
            obj = APIObjectSm()
        elif apiObject.type == 4:
            obj = APIObjectCtDef()
        elif apiObject.type == 5:
            obj = APIObjectCtData()
        elif apiObject.type == 6:
            obj = APIObjectSurfModel()
        else:
            obj = APIObject()
        return obj



    def fullUrl(self, resource):
        '''
        check if resource is selfUrl or relative path. a correct full path will be returned 
        
        :param resource: (str) to the api resource
        :returns: (str) the full resource path 
        '''
        res = urlparse(str(resource))

        if res.scheme == 'https':
            return resource
        else:
            return self.url + resource



    def optionsRequest(self, resource):
        '''
        generic options request function

        :param resource: (str) resource path
        :returns: json result or None
        '''

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
        '''
        generic get request function

        :param resource: (str) resource path
        :param rpp: (int) results per page to show
        :param page: (int) page nr to show, starts with 0
        :param include: (str) option to include more informations
        :returns: list of objects (json) or None
        '''
      
        params = dict([('rpp', rpp),('page', page),('include', include)])

   
        self._stayAlive()
        try:

            logging.debug("get(%s, params = %s)" %(self.fullUrl(resource), params))
            res = self.s.get(self.fullUrl(resource), params = params)
            if self._httpResponseCheck(res):
                if res.status_code == requests.codes.ok:
                    return res.json()
                else: 
                    logging.warning("getRequest %s failed: %s [%s]" %(resource, res, statusDescription(res.status_code) ))
                    return None
        except requests.exceptions.RequestException as err:
            print('request failed:', err)
            return None

    def downloadZip(self, resource, fp):
        '''
        download the zipfile into the given file (fp)

        :param resource: (str) download URL
        :param fp: (Path) filepath 
        :returns: None or status_code ok (200)
        '''

        self._stayAlive()

        res = self.s.get(self.fullUrl(resource), stream = True)
        if res.ok:
            with fp.open('wb') as f:
                shutil.copyfileobj(res.raw, f) 
            return res.status_code
        else:
            return None

    def downloadObject(self, obj, wp = None):
        '''
        download the object into a ZIP file based on the object name and the working directory

        :param obj: object (APIObject)
        :param wp: (Path) workpath, where to store the zip 
        :returns: None or status_code ok (200)
        '''
        
        self._stayAlive()

        fp = Path(obj.name).with_suffix('.zip')
        if wp:
            fp = Path(wp, fp)

        res = self.s.get(self.fullUrl(obj.downloadUrl), stream = True)
        if res.ok:
            with fp.open('wb') as f:
                shutil.copyfileobj(res.raw, f) 
            return res.status_code
        else:
            return None


    def removeLinks(self, resource):
        '''removes all related item from an object '''

        obj = self.getObject(resource)
        if obj.linkedObjectRelations:
            for link in obj.linkedObjectRelations:
                self.delRequest(link["selfUrl"])
        else:
            print('nothing to delete, no links available')

    def getAllPaginated(self, resource, itemlist = list()):
        '''
        returns all items as list 

        :param resource: (str) resource path
        :param itemlist: (list) of items
        :returns: list of items
        '''
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
        ''' 
        extracts the last part of the selfURL, tests if it is a number

        :param selfURL: (str) url to the object
        :returns: either None if not an ID or the object ID (int)
        :raises: ValueError
        '''
        selfURL_path = urllib.parse.urlsplit(selfURL).path
        oID = Path(selfURL_path).name

        try: 
            r = int(oID)
        except ValueError as err:
            print('no object ID in the selfUrl {0}. Reason: {1}'.format(selfURL,err))
            r = None
        return r
    
    def getObject(self, resource):
        '''retrieve an object based on the objectID

        :param resource: (str) selfUrl of the object or the (int) object ID
        :returns: the object (APIObject) 
        '''
        if isinstance(resource, int):
            resource = 'objects/' + str(resource)

        res = self.getRequest(resource)
        logging.debug("getObject %s : %s" %(resource, res))
        if res:
            obj = self.getAPIObjectType(res)
            obj.set(obj = res)
            return obj
        else:
            return res

    def putObject(self, obj):
        '''update an objects information
    
        :param obj: (APIObject) an API Object
        :returns: (APIObject) the updated object
        '''

        res = self.putRequest(obj.selfUrl, data = obj.get())
        
        if res:
            obj = self.getAPIObjectType(res)
            obj.set(obj = res)
            return obj
        else:
            return res

    def getFolder(self, resource):
        '''retrieve an folder based on the folderID

        :param resource: (str) selfUrl of the folder or the (int) folder ID
        :returns: the folder (APIFolder) 
        '''
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
        '''add data to an object

        :param resource: (str) relative path of the resource or selfUrl
        :param data: (json) data to be added to the resource
        :returns: the resource object (json)
        '''

        self._stayAlive()

        try:    
            req = self.s.post(self.fullUrl(resource), json = data)
            if req.status_code == requests.codes.created:
                return req.json()
            else: 
                return None
        except requests.exceptions.RequestException as err:
            print('request failed:',err)
            return None
  

    def putRequest(self, resource, data):
        ''' update data of an object 

        :param resource: (str) defines the relative path to the api resource
        :param data: (json) data to be added to the object
        :returns: the updated object (json)
        '''

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
        '''get an empty resource 

        :param resource: (str) resource path
        :returns: the resource object (json)
        '''

        self._stayAlive()

        req = self.s.post(self.fullUrl(resource))
        logging.debug(req)
        return req.json()

    def putRequestSimple(self, resource):

        self._stayAlive()

        req = self.s.put(self.fullUrl(resource))
        return req.json()

    def delRequest(self, resource):
        ''' generic delete request

        :param resource: (str) resource path
        :returns: status_code (int)
        '''
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
        '''
        delete an unvalidated object 

        :param obj: (APIObject) to object to delete
        :returns: status_code
        '''
        try: 
            req = self.s.delete(obj.selfUrl)
            if req.status_code == requests.codes.ok:
                print('object {0} deleted'.format(obj.id))
                return req.status_code
            else:
                print('not deleted', req.status_code)

        except requests.exceptions.RequestException as err:
            print('del request failed:',err)
            req = None

    def publishObject(self, obj):
        '''
        publisch an unvalidated object 

        :param obj: (APIObject) to object to publish
        :returns: (APIObject) returns the object
        '''
        try: 
            req = self.s.put(obj.selfUrl + '/publish')
            if req.status_code == requests.codes.ok:
                print('object {0} published'.format(obj.id))
                return self.getObject(obj.selfUrl)


        except requests.exceptions.RequestException as err:
            print('publish request failed:',err)
            req = None
        

    def searchTerm(self, resource, search ,mode = 'default'):
        ''' search a resource using oAuths
    
        :param resouce: (str) resource path
        :param search: (str) term to search for 
        :param mode: (str) search for partial match ('default') or exact match ('exact')
        :returns: list of folder objects (json)
        '''

        search = quote(search)
        if mode == 'exact':
            url = self.fullUrl(resource) + '?$filter=Term%20eq%20%27{0}%27'.format(search) 
        else:
            url = self.fullUrl(resource) + '?$filter=startswith(Term,%27{0}%27)%20eq%20true'.format(search)

        req = self.getRequest(url)
        return req.json()



    def uploadFile(self, filename, ret_response = False):
        ''' 
        push (post) a file to the server

        :param filename: (Path) the file to be uploaded
        :returns: the file object containing the related object selfUrl
        :returns: file object (APIObject)
        '''
        try:
            if isinstance(filename,str):
                logging.warning('Converting string filename to path object')
                filename = Path(filename)
            data = filename.open(mode = 'rb').read()
            ##workaround for file without file extensions
            if filename.suffix =='':
                filename = filename.with_suffix('.dcm')
            files  = { 'file' : (str(filename.name), data)}
        except:
            logging.error("opening file %s failed, aborting" %filename, exc_info= True)
            return

        res = self.s.post(self.url + 'upload', files = files)
##        if ret_response:
##                return res
        if res.status_code in [requests.codes.created, requests.codes.ok] :
            result = res.json() # {file: {selfUrl: ...}, relatedObject: {selfUrl}}
            res_file = {'selfUrl': result['file']['selfUrl']} # 'objects': [result['relatedObject']['selfUrl']] it's the second last in case of segmentations
            if res.status_code == requests.codes.ok:
                logging.warning('File was already present in %s' % Path(result['relatedObject']['selfUrl']).name )
            #obj = APIFile()
            obj = self.getAPIObjectType(res_file)
            obj.set(obj = res_file)
            return obj
        else: 
            return res.status_code


    def chunkedread(self, fp, chunksize):
        '''
        breaks the file into chunks of chunksize

        :param fp: (Path) file
        :param chunksize: (int) size in bytes of the chunk parts
        :yields: chunk
        '''

        with fp.open('rb') as f:
            while True:
                chunk = f.read(chunksize)
                if not chunk:
                    break
                yield(chunk)

    def chunkFileUpload(self, fp, chunksize = 1024*4096):
        ''' 
        upload large files in chunks of max 100 MB size

        :param fp: (Path) file
        :param chunksize: (int) size in bytes of the chunk parts, default is 4MB
        :returns: the generated API Object
        '''
        parts = math.ceil(fp.stat().st_size/chunksize)
        part = 0
        err = False
        maxchunksize = 1024 * 1024 * 100
        if chunksize < maxchunksize:
            for chunk in self.chunkedread(fp, chunksize):
                attemptsLeft = 3
                part = part + 1
                print('uploading part {0} of {1}'.format(part,parts))

                files  = { 'file' : (str(fp.name), chunk)}
                while attemptsLeft >0:
                    attemptsLeft += -1
                    res = self.s.post(self.url + 'chunked_upload?chunk={0}'.format(part), files = files)
                    if res.status_code == requests.codes.ok:
                        print('uploaded part {0} of {1}'.format(part,parts))
                        attemptsLeft = 0
                    else:
                        err = True
                        logging.warning("Error uploading file chunks: %s [attempts left %d]" %(statusDescription(res.status_code), attemptsLeft))
            if not err:
                res = None
                resource = 'chunked_upload/commit?filename={0}'.format(fp.name)
                res = self.postRequestSimple(resource)
                
                relObj = res['relatedObject']
                obj = self.getObject(relObj['selfUrl'])
                return obj
                
            else:
                return res
        else:
            print('not uploaded: defined chunksize {0} is bigger than the allowed maximum {1}'.format(chunksize, method))
            return None
 


    def getFile(self, resource):
        '''return a APIFile object
        
        :param resource: (str) resource path
        :returns: api file object (APIFile) or status code
        '''  
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
        '''return a list of file objects contained in an object

        :param obj: (APIObject) object 
        :returns: list of files(APIFiles)
        '''
        filelist = list()
        for of in obj.files:
            res = self.getFile(of['selfUrl'])
            if not isinstance(res, int):
                filelist.append(res)
        return filelist

    def fileObjectVersion(self, data):
        ''' 
        Extract VSDID and selfUrl of the related Object Version of the file after file upload

        :param data: (json) file object data
        :results: returns the id and the selfUrl of the Object Version
        '''
        #data = json.loads(data)
        f = data['file']
        obj = data['relatedObject']
        fSelfUrl = f['selfUrl']
        return obj['selfUrl'], self.getOID(obj['selfUrl'])


    def getAllUnpublishedObjects(self, resource = 'objects/unpublished'):
        ''' retrieve the unpublished objects as list of APIObject

        :param resource: (str) resource path (eg nextPageUrl) or default groups
        :param rpp: (int) results per page
        :param page: (int) page to display
        :returns: list of objects (APIObjects) 
        '''

        objects = list()
        res = self.getAllPaginated(resource)

        for item in res:
            obj = self.getObject(item.get('selfUrl'))
            objects.append(obj)
        return objects


    def getLatestUnpublishedObject(self):
        ''' searches the list of unpublished objects and returns the newest object  '''
        res = self.getRequest('objects/unpublished')
        if len(res['items']) > 0:
            obj = self.getObject(res['items'][0].get('selfUrl'))
            return obj
        else: 
            print('you have no unpublished objects')
            return None

   
                

    def getFolderByName(self, search, mode = 'default'):
        '''
        get a list of folder(s) based on a search string

        :param search: (str) term to search for 
        :param mode: (str) search for partial match ('default') or exact match ('exact')
        :returns: list of folder objects (APIFolders)
        '''   
        search = quote(search)
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
        '''
        return a list of folder object contained in a folder

        :param folder: folder (APIFolder) object
        :return folderlist: a list of folder object (APIFolder) contained in the folder
        '''

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
        '''
        return a list of object contained in a folder

        :param folder: folder (APIFolder) object
        :return objlist: a list of objects (APIFObject) contained in the folder
        '''

        objlist = list()
        if folder.containedObjects:

            for obj in folder.containedObjects:
                basic = APIBasic()
                basic.set(obj = obj)
                o = self.getObject(basic.selfUrl)
                objlist.append(o)
            return objlist
        else:
            print('the folder does not contained objects')
            return None





    def searchOntologyTerm(self, search, oType = '0', mode = 'default'):
        '''
        Search ontology term in a single ontology resource. Two modes are available to either find the exact term or based on a partial match

        :param search: (str) string to be searched
        :param oType: (int) ontlogy resouce code, default is FMA (0)
        :param mode: (str) find exact term (exact) or partial match (default)
        :returns: a list of ontology (APIOntolgy) objects or a single ontology item (APIOntology)
        '''
        search = quote(search)
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
        '''
        Retrieve an ontology entry based on the IRI

        :param oid: (int) Identifier of the entry
        :param oType: (int) Resource type, available resources can be found using the OPTIONS on /api/ontologies). Default resouce is FMA (0)
        :returns: ontology term entry (json)
        '''

        self._stayAlive()

        url = "ontologies/{0}/{1}".format(oType,oid)
        req = self.getRequest(url)
        return req.json()


    def getOntologyItem(self, resource, oType = 0):
        '''
        Retrieve an ontology item object (APIOntology)
        
        :param resource: (int or str) resource path to the of the ontology item
        :param oType: ontology type (int)
        :return onto: (APIOntology) the ontology item object
        '''

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
        ''' retrieve a list of the available licenses (APILicense)'''
        res = self.getRequest('licenses')
        licenses = list()
        if res:
            for item in iter(res['items']):
                lic = APILicense()
                lic.set(obj = item)
                licenses.append(lic)
        return licenses


    def getLicense(self, resource):
        ''' retrieve a license (APILicense)

        :param resource: (int or str) resource path to the of the license
        :return license: (APILicense) the license object
        '''
        
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
        ''' retrieve a list of the available base object rights (APIObjectRight) '''
        
        res = self.getRequest('object_rights')
        permission = list()
        
        if res:
            for item in iter(res['items']):
                perm = APIObjectRight()
                perm.set(obj = item)
                permission.append(perm)
        
        return permission

    def getObjectRight(self, resource):
        ''' retrieve a  object rights object (APIObjectRight) 
        
        :param resource: resource to the permission id (int) or selfurl (str)
        :return: perm (APIObjectRight) object
        '''

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
        '''get the list of groups

        :param resource: (str) resource path (eg nextPageUrl) or default groups
        :param rpp: (int) results per page
        :param page: (int) page to display
        :returns: list of group objects (APIGroup)
        :returns: pagination object(APIPagination)
        '''

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
        ''' retrieve a group object (APIGroup)

        :param resource: path to the group id (int) or selfUrl (str)
        :return: group (APIGroup) object
        '''
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
        ''' retrieve a user object (APIUser)

        :param resource: path to the user resource id (int) or selfUrl (str)
        :return: user (APIUser) object
        '''
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
        '''
        get the Object Rights for a permission set

        :param permset: (str) name of the permission set: available are private, protect, default, collaborate, full or a list of permission ids (list)
        :return perms: list of object rights objects (APIObjectRight) 
        '''

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
        '''
        get the list of attaced group rights of an object

        :param obj: the object (APIObject)
        :returns rights: a list of ObjectGroupRights (APIObjectGroupRight)
        '''

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
        '''
        get the list of attaced user rights of an object

        :param obj: the object (APIObject)
        :returns rights: a list of ObjectUserRights (APIObjectUserRight)
        '''

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
        ''' DEPRECATED: user postObjectGroupRights or postObjectUserRights! 
        translate a set of permissions and a group into the appropriate format and add it to the object

        :param obj: (API Object) the object you want to add the permissions to 
        :param group: (APIGroup or APIUser) group object or user object
        :param perms: (list) list of Object Rights (APIObjectRight), use getPermissionSet to retrive the ObjectRights based on the permission sets
        :param isuser: (bool) set True if the groups variable is a user. Default is False 

        :return objRight: a group or user rights (APIObjectGroupRight/APIObjectUserRight) object
        ''' 

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
        ''' translate a set of permissions and a user into the appropriate format and add it to the object

        :param obj: (API Object) the object you want to add the permissions to 
        :param group: (APIUser) user object
        :param perms: (list) list of Object Rights (APIObjectRight), use getPermissionSet to retrive the ObjectRights based on the permission sets

        :return objRight: user rights (APIObjectUserRight) object
        ''' 

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
        ''' translate a set of permissions and a group into the appropriate format and add it to the object

        :param obj: (API Object) the object you want to add the permissions to 
        :param group: (APIGroup) group object
        :param perms: (list) list of Object Rights (APIObjectRight), use getPermissionSet to retrive the ObjectRights based on the permission sets

        :return objRight: group rights (APIObjectGroupRight) object  ''' 

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
        ''' retrieve a list of modalities objects (APIModality)'''

        modalities = list()
        items = self.getAllPaginated('modalities', itemlist = list())
        if items:
            for item in items:
                modality = APIModality()
                modality.set(obj = item)
                modalities.append(modality)
            return modalities
        else:
            return items

    def getModality(self, resource):
        ''' retrieve a modalities object (APIModality)


        :param resource: (int or str) resource path to the of the license
        :return license: (APIModality) the modality object
        '''
        
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
        ''' add an object link 

        :param obj1: (APIBasic) an link object with selfUrl 
        :param obj2: (APIBasic) an link object with selfUrl
        :returns: the created object-link (json)
        '''
        link = APIObjectLink()
        link.object1 = dict([('selfUrl', obj1.selfUrl)])
        link.object2 = dict([('selfUrl', obj2.selfUrl)])
        
        return  self.postRequest('object-links', data = link.get())

    def addOntologyToObject(self, obj, ontology, pos = 0):
        ''' add an ontoly term to an object

        :param obj: (APIBasic) object
        :param ontology: (APIOntology) ontology object
        :param pos: (int) position of the ontology term, default = 1
        :return isset: (Bool) returns true if successfully added'''
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

    def postFolder(self, parent, name):
        ''' 
        creates the folder with a given name (name) inside a folder (parent) if not already exists

        :param parent: (APIFolder) the root folder
        :param name: (str) name of the folder which should be created
        :returns: (APIFolder) the folder object of the generated folder or the existing folder
        '''
         
        folder = APIFolder()
        folder.parentFolder = dict([('selfUrl', parent.selfUrl)])
        folder.name = name

        exists = False

        if parent.childFolders:
            for child in parent.childFolders:
                fold = self.getFolder(child['selfUrl'])
                if fold.name == name:
                    print('folder {0} already exists'.format(name))
                    exists = True

        if not exists:
            res = self.postRequest('folders', data = folder.get())
            folder.set(obj = res)
            print('folder {0} created, has id {1}'.format(name, folder.id))
            return folder
        else:
            return fold


    
    def createFolderStructure(self, rootfolder, filepath, parents):
        ''' 
        creates the folders based on the filepath if not already existing, 
        starting from the rootfolder

        :param rootfolder: (APIFolder) the root folder
        :param filepath: (Path) file path of the file
        :param parents: (int) number of partent levels to create from file folder 
        :returns: (APIFolder) the last folder in the tree
        '''
         
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
        '''
        add an object to the folder
    
        :param target: (APIFolder) the target folder 
        :param obj: (APIObject) the object to copy
        :returns: updated folder (APIFolder)
        '''    
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
                logging.warning(res)
                return res
        else:
            return target

    def removeObjectFromFolder(self, target, obj):
        '''
        add an object to the folder
    
        :param target: (APIFolder) the target folder 
        :param obj: (APIObject) the object to remove
        :returns: updated folder (APIFolder)
        '''  

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
        '''
        display the object information user readable format

        :param obj: object (APIObject)
        '''

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
    """docstring for APIBasic"""


    oKeys = list([
       'selfUrl'
        ])

    def __init__(self, oKeys = oKeys):
        for v in oKeys:
                setattr(self, v, None)
        
    def set(self, obj = None):
        ''' sets class variable for each key in the object to the keyname and its value'''
        if  obj:
            for v in self.oKeys:
                if v in obj: 
                    setattr(self, v, obj[v])              
        else:
            for v in self.oKeys:
                setattr(self, v, None)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return self.__dict__

    def show(self):
        '''prints the json to the console, nicely printed'''
        print(json.dumps(self.__dict__, sort_keys = True, indent = '    '))

class APIObject(APIBasic):
    '''
    API Object
    ''' 
    oKeys = list([
        'id',
        'name',
        'type',
        'description',
        'objectGroupRights',
        'objectUserRights',
        'objectPreviews',
        'createdDate',
        'modality',
        'ontologyItems',
        'ontologyItemRelations',
        'ontologyCount',
        'license',
        'files',
        'linkedObjects',
        'linkedObjectRelations',
        'downloadUrl'
        ])

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self, ):
        super(APIObject, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIObject, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIObject, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIObject, self).show()


class APIObjectRaw(APIObject):
    """docstring for APIObjectRaw"""
    oKeys = list([
        'sliceThickness',
        'spaceBetweenSlices',
        'kilovoltPeak'
        ])

    for i in APIObject.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIObject, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIObject, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIObject, self).show()

class APIObjectSeg(APIObject):
    """docstring for APIObjectSeg"""
    oKeys = list([
        'SegmentationMethod',
        'SegmentationMethodDescription'
        ])
    

    for i in APIObject.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIObject, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIObject, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIObject, self).show()


class APIObjectSm(APIObject):
    """docstring for APIObjectSm"""
    oKeys = list()

    for i in APIObject.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIObject, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIObject, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIObject, self).show()

class APIObjectCtDef(APIObject):
    """docstring for APIObjectCtDef"""
    oKeys = list()

    for i in APIObject.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIObject, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIObject, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIObject, self).show()

class APIObjectCtData(APIObject):
    """docstring for APIObjectCtData"""
    oKeys = list()

    for i in APIObject.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIObject, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIObject, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIObject, self).show()


class APIObjectSurfModel(APIObject):
    """docstring for APIObjectSurfModel"""
    oKeys = list([
        'Facet',
        'Vertex'
        ])
    

    for i in APIObject.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIObject, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIObject, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIObject, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIObject, self).show()


class APIFolder(APIBasic):
    '''
    Folder API Object
    '''
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

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIFolder, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIFolder, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIFolder, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIFolder, self).show()
  
class APIOntology(APIBasic):
    '''
    API class for ontology entries
    '''
    oKeys = list([
        'id',
        'term',
        'type',
        ])

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIOntology, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIOntology, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIOntology, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIOntology, self).show()

class APIObjectOntology(APIBasic):
    '''
    API class for object-ontology entries
    '''
    oKeys = list([
        'id',
        'type',
        'object',
        'ontologyItem',
        'position'
        ])

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIObjectOntology, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIObjectOntology, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIObjectOntology, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIObjectOntology, self).show()

class APIFile(APIBasic):
    '''
    API class for files
    '''
    oKeys = list([
        'id',
        'createdDate',
        'downloadUrl',
        'originalFileName',
        'anonymizedFileHashCode',
        'size',
        'fileHashCode',
        'objects'
        ])

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIFile, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIFile, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIFile, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIFile, self).show()

class APILicense(APIBasic):
    '''
    API class for licenses
    '''
    oKeys = list([
        'id',
        'description',
        'name',
        ])

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APILicense, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APILicense, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APILicense, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APILicense, self).show()

class APIObjectRight(APIBasic):
    '''
    API class for object rights
    '''
    oKeys = list([
        'id',
        'description',
        'name',
        ])

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIObjectRight, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIObjectRight, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIObjectRight, self).get()
   
    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIObjectRight, self).show()

class APIObjectLink(APIBasic):
    '''
    API class for object links
    '''
    oKeys = list([
        'id',
        'description',
        'object1',
        'object2',
        ])

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIObjectLink, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIObjectLink, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIObjectLink, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIObjectLink, self).show()

class APIModality(APIBasic):
    '''
    API class for modalities
    '''
    oKeys = list([
        'id',
        'description',
        'name'
        ])

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIModality, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIModality, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIModality, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIModality, self).show()

class APIObjectGroupRight(APIBasic):
    '''
    API class for object group rights
    '''
    oKeys = list([
        'id',
        'relatedObject',
        'relatedRights',
        'relatedGroup'
        ])

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIObjectGroupRight, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIObjectGroupRight, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIObjectGroupRight, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIObjectGroupRight, self).show()

class APIObjectUserRight(APIBasic):
    '''
    API class for object user rights
    '''
    oKeys = list([
        'id',
        'relatedObject',
        'relatedRights',
        'relatedUser'
        ])

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIObjectUserRight, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIObjectUserRight, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIObjectUserRight, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIObjectUserRight, self).show()

class APIGroup(APIBasic):
    '''
    API class for groups
    '''
    oKeys = list([
        'id',
        'Chief',
        'name'
        ])

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIGroup, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIGroup, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIGroup, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIGroup, self).show()

class APIUser(APIBasic):
    '''
    API class for users
    '''
    oKeys = list([
        'id',
        'username'
        ])

    for i in APIBasic.oKeys:
        oKeys.append(i)

    def __init__(self):
        super(APIUser, self).__init__(self.oKeys) 

    def set(self, obj = None):
        super(APIUser, self).set(obj = obj)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return super(APIUser, self).get()

    def show(self):
        '''prints the json to the console, nicely printed'''
        super(APIUser, self).show()

class APIPagination(object):
    '''
    API class for Pagination results
    '''
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
        ''' sets class variable for each key in the object to the keyname and its value'''
        if  obj:
            for v in self.oKeys:
                if v in obj: 
                    setattr(self, v, obj[v])              
        else:
            for v in self.oKeys:
                setattr(self, v, None)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return self.__dict__

    def show(self):
        '''prints the json to the console, nicely printed'''
        print(json.dumps(self.__dict__, sort_keys = True, indent = '    '))                             
                                         
class APIToken(object):
    '''
    API class to work with the tokens
    '''
    oKeys = list([
        'tokenType',
        'tokenValue'
        ])

    def __init__(self, oKeys = oKeys):
        for v in oKeys:
                setattr(self, v, None)

        
    def set(self, obj = None):
        ''' sets class variable for each key in the object to the keyname and its value'''
        if  obj:
            for v in self.oKeys:
                if v in obj: 
                    setattr(self, v, obj[v])              
        else:
            for v in self.oKeys:
                setattr(self, v, None)

    def get(self):
        '''transforms the class object into a json readable dict'''
        return self.__dict__

    def show(self):
        '''prints the json to the console, nicely printed'''
        print(json.dumps(self.__dict__, sort_keys = True, indent = '    '))
