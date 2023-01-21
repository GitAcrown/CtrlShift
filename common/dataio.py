from pathlib import Path
from tinydb import TinyDB
import sqlite3

DEFAULT_DATA_PATH = "database/"
DEFAULT_PACKAGE_PATH = "cogs/packages/"

def get_tinydb_database(group_name: str, subgroup_name: str = "GLOBAL") -> TinyDB:
    """Récupérer la base de données TinyDB.
    Si le fichier n'existe pas, il est créé automatiquement 

    :param group_name: Nom du groupe (le plus souvent le nom du Cog)
    :param subgroup_name: Nom du sous-groupe (Sous-division du groupe)
    :return: TinyDB
    """
    path = Path(DEFAULT_DATA_PATH + group_name)
    path.mkdir(parents=True, exist_ok=True)
    return TinyDB(str(path / f'{subgroup_name}.json'))

def get_sqlite_database(folder_name: str, db_name: str = 'global') -> sqlite3.Connection:
    """Récupérer la base ded données SQLite. 
    Si elle existe pas, sera créée automatiquement

    :param folder_name: Nom du dossier de stockage
    :param db_name: Nom de la base de données, par défaut 'global'
    :return: sqlite3.Connection
    """
    module_folder = Path(DEFAULT_DATA_PATH + folder_name)
    module_folder.mkdir(parents=True, exist_ok=True)
    db_file = module_folder / f"{db_name}.db"
    
    conn = sqlite3.connect(str(db_file))
    return conn

def get_package_path(name: str) -> str:
    """Renvoie le chemin vers les packs de données d'un module

    :param name: Nom du module
    :return: str
    """
    return DEFAULT_PACKAGE_PATH + name
