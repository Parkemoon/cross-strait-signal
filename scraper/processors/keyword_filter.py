"""
Keyword pre-filter for Cross-Strait Signal.
Checks articles against a relevance keyword list BEFORE sending to the AI.
No API calls — just fast string matching. This saves 80%+ of your API budget.
"""

# An article MUST mention at least one of these to be considered relevant
# This prevents Iran/Russia/Ukraine military news from getting through
GEOGRAPHIC_ANCHORS = [
    # Simplified Chinese
    "台湾", "台海", "两岸", "大陆", "国台办", "中国", "北京", "解放军",
    "东部战区", "南部战区", "中美", "中日", "南海", "东海", "一中",
    "统一", "台独", "习近平", "王毅", "赖清德", "萧美琴", "李强", "顾立雄", "郑丽文", "韩国瑜", "何卫东",
    "国民党", "民进党", "民主进步党", "民众党", "统促党", "新党", "亲民党", "基进党",
    # Traditional Chinese
    "台灣", "兩岸", "大陸", "國台辦", "中國", "東部戰區", "南部戰區", "國台辦", "海基會", "海協會",
    "統一", "台獨", "習近平", "賴清德", "蕭美琴", "李強", "王毅", "顧立雄", "鄭麗文", "韓國瑜", "何衛東",
    "國民黨", "民進黨", "民主進步黨", "民眾黨", "統促黨", "新黨", "親民黨", "基進黨",
    # English
    "taiwan", "taipei", "cross-strait", "cross strait", "beijing",
    "prc", "china", "chinese", "pla", "xi jinping", "wang yi",
    "lai ching-te", "one china", "strait", "mainland china",
    "south china sea", "east china sea", "indo-pacific",
]

# Keywords that indicate cross-strait / geopolitical relevance
# An article matching ANY of these gets sent to the AI for full analysis
RELEVANCE_KEYWORDS = {
    "cross_strait": {
        "zh": [
            "台湾", "台灣", "两岸", "兩岸", "统一", "統一", "独立", "獨立",
            "台独", "台獨", "分裂势力", "一中", "一个中国", "一個中國", "九二共识", "九二共識",
            "国台办", "國台辦", "陆委会", "陸委會", "海协会", "海協會", "海基会", "海基會",
            "台海", "台湾海峡", "台灣海峽", "大陆", "大陸", "内地", "內地",
            "同胞", "和平统一", "和平統一", "一国两制", "一國兩制",
            "反分裂", "武统", "武統", "促统", "促統",
        ],
        "en": [
            "taiwan", "cross-strait", "cross strait", "taipei",
            "unification", "reunification", "independence",
            "one china", "1992 consensus", "taiwan strait",
            "mainland affairs", "taiwan affairs office",
            "dpp", "kmt", "kuomintang", "democratic progressive",
        ],
    },
    "military_defense": {
        "zh": [
            "解放军", "解放軍", "军事", "軍事", "演习", "演習", "实弹", "實彈",
            "东部战区", "東部戰區", "南部战区", "南部戰區",
            "火箭军", "火箭軍", "导弹", "導彈", "航母", "舰队", "艦隊",
            "歼", "殲", "轰", "轟", "战斗机", "戰鬥機", "军舰", "軍艦",
            "海军", "海軍", "空军", "空軍", "陆军", "陸軍",
            "防空识别区", "防空識別區", "中线", "中線",
            "巡航", "战备", "戰備", "国防", "國防", "汉光", "漢光",
            "军演", "軍演", "武器", "弹药", "彈藥", "潜舰", "潛艦",
            "海警", "海巡", "不对称作战", "不對稱作戰",
            "国防部", "國防部", "参谋", "參謀","共軍", "共軍",
        ],
        "en": [
            "pla", "military", "exercise", "drill", "missile",
            "carrier", "warship", "fighter jet", "bomber",
            "adiz", "median line", "combat readiness",
            "navy", "air force", "army", "coast guard",
            "eastern theatre", "southern theatre",
            "defense ministry", "defence ministry",
            "arms sale", "weapon", "submarine",
        ],
    },
    "diplomacy_politics": {
        "zh": [
            "外交", "外交部", "发言人", "發言人", "严正交涉", "嚴正交涉",
            "强烈不满", "強烈不滿", "坚决反对", "堅決反對",
            "核心利益", "红线", "紅線", "底线", "底線",
            "制裁", "反制", "报复", "報復","總統府"
            "习近平", "習近平", "李强", "李強", "王毅",
            "赖清德", "賴清德", "萧美琴", "蕭美琴", "顾立雄", "顧立雄",
            "郑丽文", "鄭麗文", "韩国瑜", "韓國瑜",
            "张又侠", "張又俠", "何卫东", "何衛東",
            "印太", "南海", "南海", "东海", "東海",
            "中美", "中日", "中欧", "中歐",
            "邦交", "断交", "斷交", "建交",
            "联合国", "聯合國", "世卫", "世衛",
            "國民黨", "民進黨", "民主進步黨", "民眾黨", "統促黨", "新黨", "親民黨", "基進黨",
        ],
        "en": [
            "foreign ministry", "spokesperson", "mfa",
            "sanctions", "diplomatic", "solemn representation",
            "firmly oppose", "core interest", "red line",
            "xi jinping", "li qiang", "wang yi",
            "lai ching-te", "hsiao bi-khim", "wellington koo",
            "indo-pacific", "south china sea", "east china sea",
            "aukus", "quad", "nato",
            "state visit", "summit", "bilateral",
            "kuomintang", "dpp", "kmt", "democratic progressive party", "tpp", "taiwan people's party", "new party", "people first party", "taiwan statebuilding party",
        ],
    },
    "economy_trade": {
        "zh": [
            "关税", "關稅", "贸易", "貿易", "经济", "經濟",
            "供应链", "供應鏈", "半导体", "半導體", "芯片", "晶片",
            "稀土", "出口管制", "进口", "進口", "出口",
            "ECFA", "服贸", "服貿", "货贸", "貨貿",
            "一带一路", "一帶一路", "投资", "投資",
            "台商", "陆资", "陸資", "外资", "外資",
            "科技战", "科技戰", "脱钩", "脫鉤",
        ],
        "en": [
            "tariff", "trade war", "supply chain", "semiconductor",
            "chip", "rare earth", "export control",
            "ecfa", "investment", "economic coercion",
            "belt and road", "bri", "decoupling",
            "tech war",
        ],
    },
    "grey_zone_info_war": {
        "zh": [
            "认知作战", "認知作戰", "假信息", "假訊息",
            "统战", "統戰", "渗透", "滲透",
            "网络攻击", "網路攻擊", "黑客", "駭客",
            "无人机", "無人機", "气球", "氣球",
            "海底电缆", "海底電纜", "抽砂", "抽砂船",
            "灰色地带", "灰色地帶",
        ],
        "en": [
            "cognitive warfare", "disinformation", "misinformation",
            "united front", "infiltration", "cyber attack",
            "drone", "balloon", "undersea cable", "sand dredging",
            "grey zone", "gray zone", "hybrid warfare",
        ],
    },
}


def check_relevance(title, content, language="zh"):
    """
    Check if an article is relevant to cross-strait monitoring.
    
    Two-gate filter:
    1. Must mention a geographic anchor (Taiwan, China, PLA, etc.)
    2. Must also match at least one topic keyword
    
    Returns:
        tuple: (is_relevant: bool, matched_categories: list, matched_keywords: list)
    """
    text = f"{title} {content}".lower()
    
    # Gate 1: Must have a geographic anchor
    has_anchor = False
    for anchor in GEOGRAPHIC_ANCHORS:
        if anchor.lower() in text:
            has_anchor = True
            break
    
    if not has_anchor:
        return False, [], []
    
    # Gate 2: Must also match a topic keyword
    matched_categories = []
    matched_keywords = []
    
    for category, lang_keywords in RELEVANCE_KEYWORDS.items():
        for lang in ["zh", "en"]:
            for keyword in lang_keywords.get(lang, []):
                if keyword.lower() in text:
                    if category not in matched_categories:
                        matched_categories.append(category)
                    matched_keywords.append(keyword)
    
    is_relevant = len(matched_categories) > 0
    return is_relevant, matched_categories, matched_keywords