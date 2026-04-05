"""
Keyword pre-filter for Cross-Strait Signal.
Directional filter: 
- PRC sources must mention Taiwan/ROC territory
- Taiwan sources must mention PRC/mainland/HK/Macau
This replaces the previous broad keyword taxonomy approach.
"""

# What PRC-origin articles must mention to be relevant
PRC_MUST_MENTION_TAIWAN = [
    # Simplified Chinese
    "台湾", "台海", "两岸", "台独", "台澎金马",
    "金门", "马祖", "澎湖", "台北", "高雄", "台中",
    "赖清德", "萧美琴", "顾立雄", "郑丽文", "韩国瑜",
    "国民党", "民进党", "民主进步党", "民众党", "基进党",
    "海基会", "陆委会", "国台办",
    "中华民国", "中华台北",
    # Traditional Chinese (may appear in PRC sources quoting Taiwan)
    "台灣", "兩岸", "台獨", "金門", "馬祖", "澎湖",
    "賴清德", "蕭美琴",
    # English
    "taiwan", "taipei", "kinmen", "matsu", "penghu",
    "cross-strait", "cross strait", "taiwan strait",
    "republic of china", "roc ",
]

# What Taiwan-origin articles must mention to be relevant  
TW_MUST_MENTION_PRC = [
    # Traditional Chinese
    "中國", "中共", "共產黨", "解放軍", "共軍",
    "中華人民共和國", "兩岸", "大陸", "北京", "習近平",
    "國台辦", "海協會", "東部戰區", "南部戰區",
    "香港", "澳門", "一國兩制", "九二共識",
    "王毅", "李強", "何衛東",
    # Simplified Chinese (may appear in Taiwan sources)
    "中国", "中共", "解放军", "共军", "北京", "习近平",
    "国台办", "海协会", "东部战区",
    "香港", "澳门", "一国两制", "九二共识",
    # English
    "china", "prc", "pla ", "beijing", "xi jinping",
    "communist party", "ccp", "hong kong", "macau",
    "people's liberation army",
]


def check_relevance(title, content, language="zh", source_country=None):
    """
    Directional relevance check.
    
    PRC sources: must mention Taiwan or ROC territory
    Taiwan sources: must mention PRC, mainland, HK, or Macau
    Unknown sources: fall back to checking both lists
    
    Returns:
        tuple: (is_relevant: bool, matched_categories: list, matched_keywords: list)
    """
    text = f"{title} {content}".lower()

    if source_country in ('PRC', 'SG'):
        anchor_list = PRC_MUST_MENTION_TAIWAN
    elif source_country == 'TW':
        anchor_list = TW_MUST_MENTION_PRC
    else:
        # Fallback: check both directions
        anchor_list = PRC_MUST_MENTION_TAIWAN + TW_MUST_MENTION_PRC

    matched_keywords = [a for a in anchor_list if a.lower() in text]
    is_relevant = len(matched_keywords) > 0

    # Return format kept consistent with rest of pipeline
    # categories list repurposed to carry source direction
    categories = ['cross_strait_prc'] if source_country == 'PRC' else ['cross_strait_tw']
    return is_relevant, categories, matched_keywords