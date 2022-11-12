from tinydb import TinyDB, Query
from pathlib import Path

DEFAULT_DATA_PATH = "database/"

def get_database(group_name: str, subgroup_name: str = "GLOBAL") -> TinyDB:
    """Récupérer la base de données TinyDB.
    Si le fichier n'existe pas, il est créé automatiquement 

    :param group_name: Nom du groupe (le plus souvent le nom du Cog)
    :param subgroup_name: Nom du sous-groupe (Sous-division du groupe)
    :return: TinyDB
    """
    path = Path(DEFAULT_DATA_PATH + group_name)
    path.mkdir(parents=True, exist_ok=True)
    return TinyDB(str(path / f'{subgroup_name}.json'))
    
