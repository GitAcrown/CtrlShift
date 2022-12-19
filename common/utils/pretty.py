# Fonctions d'affichage transverses

def bar_chart(value: int, max_value: int, char_value: int = 1, use_half_bar: bool = True):
    """Crée une barre en ASCII représentant une progression ou une proportion

    :param value: Valeur à représenter
    :param max_value: Limite haute que peut prendre la barre
    :param char_value: La valeur en % représentée par un seul caractère
    :param use_half_bar: S'il faut utiliser une demie-barre pour représenter un reste
    """
    nb_bars = (value / max_value) * 100 / char_value
    bars = '█' * int(nb_bars)
    if not nb_bars.is_integer() and use_half_bar:
        bars += '▌'
    return bars