# Apache Airflow PowerBI Connector
## Description
This is a sensor, hook, and operator to refresh powerbi datasets

## Setting up an airflow connection

Create a connection in airflow with the following properties: \
type: http \
login: Client_ID
Password: Client_secret \
extra: \ 
```json
{
  "tenant_id": "TENANT_ID"
}
```