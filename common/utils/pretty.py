# Fonctions d'affichage transverses
from typing import Union

def bar_chart(value: int, max_value: int, char_value: int = 1, use_half_bar: bool = True) -> str:
    """Crée une barre en ASCII représentant une progression ou une proportion

    :param value: Valeur à représenter
    :param max_value: Limite haute que peut prendre la barre
    :param char_value: La valeur en % représentée par un seul caractère
    :param use_half_bar: S'il faut utiliser une demie-barre pour représenter un reste
    :returns: str
    """
    nb_bars = (value / max_value) * 100 / char_value
    bars = '█' * int(nb_bars)
    if not nb_bars.is_integer() and use_half_bar:
        bars += '▌'
    return bars

def troncate_text(text: str, length: int, add_ellipsis: bool = True) -> str:
        """Retourne une version tronquée du texte donné

        :param length: Nombre de caractères max. voulus
        :param add_ellipsis: S'il faut ajouter ou non '…' lorsque le message est tronqué, par défaut True
        :return: str
        """
        if len(text) <= length:
            return text
        return text[:length] + '…' if add_ellipsis else ''
    
def humanize_number(number: Union[int, float], separator: str = ' ') -> str:
    """Formatte un nombre pour qu'il soit plus lisible

    :param number: Nombre à formatter
    :param separator: Séparateur entre groupes de 3 chiffres, par défaut ' '
    :return: str
    """
    return f'{number:,}'.replace(',', separator)

def codeblock(text: str, lang: str = "") -> str:
    """Retourne le texte sous forme d'un bloc de code

    :param text: Texte à formatter
    :param lang: Langage à utiliser, par défaut "" (aucun)
    :return: str
    """
    return f"```{lang}\n{text}\n```"
