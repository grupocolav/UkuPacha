import sys
import cx_Oracle
import datetime
import pandas as pd
import json
from bson import ObjectId
from bson import BSONSTR
from bson.codec_options import TypeCodec
from bson.codec_options import TypeRegistry
from bson.codec_options import CodecOptions


class OracleLOBCodec(TypeCodec):
    python_type = cx_Oracle.LOB    # the Python type acted upon by this type codec
    bson_type = BSONSTR   # the BSON type acted upon by this type codec

    def transform_python(self, value):
        """Function that transforms a custom type value into a type
        that BSON can encode."""
        return ''.join(value.read())

    def transform_bson(self, value):
        """Function that transforms a vanilla BSON type value into our
        custom type."""
        return value


oraclelob_codec = OracleLOBCodec()
oracle_codec_options = CodecOptions(
    type_registry=TypeRegistry([oraclelob_codec]))


class JsonEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for oracle graph,
    all the customized stuff for encoding required for our endpoints
    can be handle in this class
    """

    def default(self, o):
        if isinstance(o, pd.Timestamp):
            return str(o)
        if isinstance(o, type(pd.NaT)):
            return None
        if isinstance(o, cx_Oracle.LOB):
            # https://cx-oracle.readthedocs.io/en/7.1/lob.html#LOB.read
            # WARNING: es posible que no lea todo el contenido,
            # de momento solo esta en pocos campos, no con contenidos muy largos.
            # ex: tabla RE_PROYECTO_INSTITUCION campo NRO_VALOR
            return ''.join(o.read())
        if isinstance(o, datetime.datetime):
            try:
                return datetime.datetime.strftime(o, format='%Y%m%d')
            except ValueError:
                return None
        if isinstance(o, pd.Series):
            return o.to_dict()
        if isinstance(o, ObjectId):
            return str(o)
        return json.JSONEncoder.default(self, o)


class Utils:
    def __init__(self, user="system", password="colavudea", dburi="localhost:1521"):
        self.connection = cx_Oracle.connect(user=user,
                                            password=password,
                                            dsn=dburi,
                                            threaded=True)

    def request(self, query):
        """
        Perform a request to the Oracle with a query.

        Parameters:
        ----------
        query:str
            SQL query

        Returns:
        ----------
            dataframe with the results
        """
        # https://www.oracle.com/technical-resources/articles/embedded/vasiliev-python-concurrency.html
        # alternavite to evalute if the code above doesnt work
        # https://stackoverflow.com/questions/60887128/how-to-convert-sql-oracle-database-into-a-pandas-dataframe

        try:
            df = pd.read_sql(query, con=self.connection)
        except cx_Oracle.Error as error:
            print(error)
            # if someting is failing with the connector is better to quit.
            sys.exit(1)
        return df

    def get_keys(self, table, ktype="P"):
        """
        Returns the keys from the table on Oracle DB,

        Parameters:
        ----------
        db:str
            database name ex: udea_cv
        table:str
            table on database ex: EN_PRODUCTO
        ktype:str
            key type, opetions P (Primary), F (Foreing)

        Returns:
        ---------
            pandas dataframe with key information
        """
        query = f"SELECT cols.table_name, cols.column_name, cols.position, cons.status, cons.owner \
                FROM all_constraints cons, all_cons_columns cols WHERE cols.table_name = '{table}' \
                AND cons.constraint_type = '{ktype}' AND cons.constraint_name = cols.constraint_name \
                AND cons.owner = cols.owner  ORDER BY cols.table_name, cols.position"
        return self.request(query)

    def get_tables(self, db):
        """
        Returns the names of the tables available for a given db name.

        Parameters:
        ----------
        db:str
            database name ex: UDEA_CV

        Returns:
        ----------
            list of tables names 
        """
        query = f"SELECT * FROM all_tables WHERE OWNER='{db}'"
        df = self.request(query)
        return list(df["TABLE_NAME"].values)

    def get_db_data(self, db):
        """
        Returns a dictionary where the keys are the tables and the values the dataframes with the data.

        Parameters:
        ----------
        db:str
            Database name

        Returns:
        ----------
            Dictionary with all the data for the given database.
        """
        data = {}
        tables_names = self.get_tables(db)
        for table in tables_names:
            query = f"SELECT * FROM {db}.{table}"
            data[table] = self.request(query)
        return data

    def request_register(self, db, keys, table):
        query = f"SELECT * FROM {db}.{table} WHERE "
        for key in keys:
            query += f" {key}='{keys[key]}' AND"
        query = query[0:-3]
        req = self.request(query)
        return req


def is_dict(data):
    tname = type(data).__name__
    if tname == 'dict':
        return True
    return False


def is_list(data):
    tname = type(data).__name__
    if tname == 'list':
        return True
    return False


def is_serie(data):
    tname = type(data).__name__
    if tname == 'dict' or tname == 'list':
        return False
    return True


def section_exist(section, keys):
    for i in list(keys):
        if section == i:
            return True
    return False


def table_exists(fields, table):
    for i in list(fields.keys()):
        if table == i:
            return True
    return False


def parse_table(fields, table_name, data_row, filters_function=None):
    data = {}
    # WARNING HERE; AT THE MOMENT I AM NOT PARSING FIELDS WITH ALIAS
    if table_exists(fields, table_name):
        if filters_function:
            data_row = filters_function(table_name, data_row)
        if is_dict(data_row):
            data = data_row
        else:
            data = data_row.to_dict()
    return data


def replace_graph_db_field(graph, value_old, value_new):
    """
    Allows to replace the filed "DB": "__VALUE__" for "DB": "__NEW_VALUE__"
    example for scienti:
        "DB": "__CVLAC__" for "DB": "UDEA_CV"

    Parameters:
    ----------
    graph:dict
        dictionary with the model
    value_old:str
        current value for "DB" field
    value_new:str
        new value for "DB" field

    Returns:
    ----------
        dict with the new graph with the field "DB" changed. 
    """
    graph_str = json.dumps(graph)
    graph_str = graph_str.replace(
        f'"DB": "{value_old}"', f'"DB": "{value_new}"')
    return json.loads(graph_str)

# def parse_table(fields,table_name,data_row,remove_nulls=True):
#    data={}
#    if table_exists(fields,table_name):
#        for field,alias in fields[table_name]["fields"].items():
#            if remove_nulls:
#                if data_row[field]:
#                    data[alias] = data_row[field]
#            else:
#                data[alias] = data_row[field]
#    return data
