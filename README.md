# README #

This library implements a client for the REST API of the virtualskeletondatabase (www.virtualskeleton.ch). It supports authentication, general queries, and specific requests such as image upload/download, object linking and right management. Examples are provided in the examples directory. Please use 'demo.virtualskeleton.ch' for testing purposes.

## Module documentation
-[http://sicasfoundation.github.io/vsdConnect/](http://sicasfoundation.github.io/vsdConnect/)

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
1. clone the repo

    git clone https://github.com/SICASFoundation/vsdConnect

2. Install the package with dependencies

    pip install vsdConnect

    or, if you want to edit the source:

    pip install --editable vsdConnect

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

## Problems
* The server response is very slow if you have 50+ folders. VSD-connect makes a request to the server for each folder. Therefore, I will be slow if you have a lot of folders and use the folder methods. You should then use the getRequest function and create your APIFolder object locally.

## Get Started

from vsdConnect import connectVSD

api = connectVSD.VSDConnecter()
obj = api.getObject(21)
print(obj.selfUrl, obj.name)



