# ZwickRoell-START-Hack-2026
# Setup

## Recommended Tools
### MongoDB Compass
To explore the MongoDB, we recommend mongodb compass
> https://www.mongodb.com/products/tools/compass

### Docker (Desktop)
to use the mongodb docker image, you will need docker. For windows, we recommend using docker desktop:
https://www.docker.com/products/docker-desktop/

### MCP Inspector
A useful Tool to test MCP functionality
https://modelcontextprotocol.io/docs/tools/inspector

## Get the MongoDB via Docker

1. generate a personal access token (PAT classic) in github. It only needs the **read:packages** permission
2. open a Terminal and type the following to authenticate docker:
	1. `echo "YOUR_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_NAME --password-stdin`
3. pull the image via:
	1. `docker pull ghcr.io/svenstamm/txp-mongo:latest`
    2. if you get a access denied, please check in with Adrian or me (Sven Stamm) if you got the necessary permissions 
4. The mongodb server is running without Authentication, on the default ports. Start the image by running
5. `docker run -d -p 27017:27017 --name txp-database ghcr.io/svenstamm/txp-mongo:latest`
6. On first start, the mongodb is getting setup, this may take a little bit, you can check the logs to view the progress
7. If, after the initial mongodb creation the process exits with a 'adress already in use', restart the image to get the mongodb running via `docker container start [containerId]`

# Data Explanation

## UUIDs
In many areas of the Data you will stumble upon UUIDs. We tried to migrate them as best we could, but on some places they are still integral.

#### Valuecolumns
this is the propably biggest source for UUIDs. The structure of a valucolumn entry, consist of two important metadatas: `refId` and `childId`
- `refId` is a reference to the source test `_id`
- `childId` is id constructed by the `[test.valuecolumns._id].[test.valuecolumn.valuetableId]
- The UUIDs in `childId` is a reference to the **type** of value stored there. In the repository you will find files containing translations for these UUIDs, as well as the possible unittables.
	- for Results (valuecolumn has only a single value), take a look at the file `TestResultTypes`
	- for Measurements, take a look at the `channelParameterMap`
- some `test.valuecolumn._id` end with a _key - they can be safely ignored and weren't migrated into this test dataset

## OpenAI Api Key
If you don't have access to a llm, you can use the following API Key:

> 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
 
## Reading and inspiration

- https://t3n.de/news/claude-wird-zum-daten-tool-anthropic-bringt-klickbare-charts-in-den-chat-auch-fuer-free-user-1733872/
