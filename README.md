# xc-opensource-trading-api-ws
CrossClassify open source trading app backend API (WebSocket)

![xc-opensource-trading-api-ws Logo](https://www.crossclassify.com/static/media/app-logo.5f201a1bce0dda55e1e82e3d3d78c445.svg)

xc opensource trading api is a web socket server for xc trading app written in python using autobahn.

## Table of Contents
 
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [Credits](#credits)
- [License](#license)

## Prerequisites

Before installing and using this server, you should get some api keys and create some accounts.

1. We deployed this server to **GCP cloud run** service. so you may want to create a GCP account for deploying there.
2. We use **GCP pub/sub** for connection between different containers. Be sure to create a key file for pub/sub to work.
3. we use **finnhub** for getting live stock prices. you can get a free api key in their website.
4. Our database is **mongoDB**. So you may want to have a URI for your own mongoDB server.

## Installation

To install the xc opensource trading api, follow these steps:

1. Clone this repository.
2. Install the requirements.
3. Run server file.

```bash
git clone https://github.com/crossclassify/xc-opensource-trading-api-ws.git
cd xc-opensource-trading-api-ws
pip install -r requirements.txt
python server.py
```

## Usage

To use the xc opensource trading api, you have to customize it:

1. Open the server.py file in your editor.
2. Go to config variables section after import lines.
3. Write your gcp key file address in GOOGLE_APPLICATION_CREDENTIALS section.
```python
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'ADDRESS-OF-YOUR-GCP-KEY.JSON-FILE'
```
4. Write your mongoDB URI and and db name in MONGO section.
```python
MONGOURI = "YOUR-MONGODB-URI"
db = client["YOUR-MONGO-DB-NAME"]
```
5. Write your GCP project id and pub/sub name in GCP section.
```python
PUBSUB_PRICE = 'YOUR-PUBSUB-NAME'
GOOGLE_PROJECT_ID = 'YOUR-GOOGLE-PROJECT-ID'
```
6. Write your finnhub api key in FINNHUB section.
```python
FINNHUB_API_KEY = "YOUR-FINNHUB-KEY"
```

Now you can run the server and use it on your own.

## Contributing

Contributions are welcome! To contribute to the Random Name Generator, follow these steps:

1. Fork this repository.
2. Create a new branch with your changes: `git checkout -b my-feature-branch`
3. Make your changes and commit them: `git commit -m "Add my feature"`
4. Push to the branch: `git push origin my-feature-branch`
5. Create a new pull request.

Please follow our code of conduct when contributing to this project.

## Credits

The Random Name Generator uses the following external libraries:

- [Autobahn](https://autobahn.readthedocs.io/en/latest/) for creating web socket servers.
- [Finnhub](https://finnhub.io/) for getting live stock prices.
- [yfinance](https://pypi.org/project/yfinance/) for historical stock prices.

## License

The Random Name Generator is licensed under the Apache-2.0 License.

---

For questions or support, please contact us.
