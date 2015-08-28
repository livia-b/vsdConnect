# README #

This library implements a client for the REST API of the virtualskeletondatabase (www.virtualskeleton.ch). It supports authentication, general queries, and specific requests such as image upload/download, object linking and right management. Examples are provided in the examples directory. Please use 'demo.virtualskeleton.ch' for testing purposes.

## What is in this Fork
- Pyhton 3 (3.4.3)
- usage of **requests** package instead of urllib2
- usage of **pathlib** instead of os.path
- usage of **PyJWT** for jwt.io authentication [PyJWT](https://github.com/jpadilla/pyjwt)
- support file poster.py removed (no needed with requests)
- introduction of API classes

## Recent updates
- Added SAML auth 
- Added chunk Upload (upload files > 500 MB) 
- Added JWT auth

### What is this repository for? ###

* Quick summary: connect to vsd
* Version: 0.2

### How do I get set up? ###
1. install dependencies    
    
    pip install requests
    pip install PyJWT

2. get the code and 
3. Just add the source directory to your PYTHONPATH

### Contribution guidelines ###

* Write exception handling
* Writing tests
* Code review
* Adding sockets/timeouts/retries
* Adding more stable support for pagination
* Add general file upload
* Write some sort of GUI example

### Who do I talk to? ###

* Repo owner or admin
* Other community or team contact

## Get Started

import connectVSD

api = connectVSD.connectVSD()
obj = api.getObject(21)
print(obj.selfUrl, obj.name)



