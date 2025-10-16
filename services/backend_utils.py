# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import pandas as pd
import lunarcalendar
from collections import Counter
from pydantic import BaseModel
import pytz
from pymongo import MongoClient
import re
import ast
import random
import requests
from requests.adapters import HTTPAdapter, Retry
import threading
import time
import builtins
import copy
from typing import Any, Dict
from config import GPT_API_KEY, MONGO_URL, GPT_URL

def safe_print(*args, **kwargs):
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        sanitized = []
        for arg in args:
            if isinstance(arg, str):
                sanitized.append(arg.encode("utf-8", "ignore").decode("ascii", "ignore"))
            else:
                sanitized.append(repr(arg).encode("utf-8", "ignore").decode("ascii", "ignore"))
        builtins.print(*sanitized, **kwargs)

print = safe_print

DEBUG_ENABLED = False

def debug_print(*args, **kwargs):
    if DEBUG_ENABLED:
        safe_print(*args, **kwargs)


def _now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def call_gpt(text_input):
    # url = "http://10.104.0.5:32124/api/chat/completions"
    url = GPT_URL
    headers = {"Content-Type": "application/json"}
    if not GPT_API_KEY:
        raise RuntimeError("GPT_API_KEY is not configured. Set it via Streamlit secrets or environment variables.")
    headers["Authorization"] = f"Bearer {GPT_API_KEY}"
    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": text_input
            }
        ],
        # "max_tokens": 50,
        # "temperature": 0.3,
        # "stream": False
    }

    retries = Retry(
        total=3,
        connect=3,
        read=2,
        backoff_factor=1.5,
        status_forcelist=(408, 409, 429, 500, 502, 503, 504),
        allowed_methods=None,
    )
    adapter = HTTPAdapter(max_retries=retries)

    try:
        with requests.Session() as session:
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            response = session.post(url, json=payload, headers=headers, timeout=(5, 60))
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"GPT request failed: {exc}") from exc

    status = response.status_code
    try:
        r = response.json()
    except ValueError:
        print("call_gpt: non-JSON response", response.text)
        return status, response.text

    debug_print('r', r)

    if status != 200:
        error_message = ""
        if isinstance(r, dict):
            error_message = r.get("error") or r.get("message") or str(r)
        if not error_message:
            error_message = str(r)
        return status, error_message

    choices = r.get('choices')
    if not choices:
        return status, "Missing 'choices' in GPT response"

    content = choices[0]['message']['content']

    debug_print('-'*50)
    debug_print('res:', r)
    debug_print('-'*50)
    
    return status, content


def _update_gpt_status(line_id: str, **updates: Any) -> Dict[str, Any]:
    entry = BG_STD_TASK_STATUS.setdefault(line_id, {"line_id": line_id})
    entry.update(updates)
    entry["updated_at"] = _now_iso()
    return entry


def get_gpt_task_status(line_id: str) -> Dict[str, Any] | None:
    entry = BG_STD_TASK_STATUS.get(line_id)
    if entry is None:
        return None
    return copy.deepcopy(entry)

def format_thai_date(date_str: str) -> str:
    # แปลง string เป็น datetime
    date_obj = datetime.strptime(date_str, "%Y_%m_%d")
    
    # แปลงปี ค.ศ. เป็น พ.ศ.
    thai_year = date_obj.year + 543
    
    # ชื่อวันและเดือนภาษาไทย
    thai_days = ["วันจันทร์", "วันอังคาร", "วันพุธ", "วันพฤหัสบดี", "วันศุกร์", "วันเสาร์", "วันอาทิตย์"]
    thai_months = [
        "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
    ]
    
    day_name = thai_days[date_obj.weekday()]
    day = date_obj.day
    month_name = thai_months[date_obj.month]

    return f"{day_name}ที่ {day} {month_name} พ.ศ.{thai_year}"

CD = None
GIF = None

BG_STD_TASK = []
BG_STD_TASK_STATUS: Dict[str, Dict[str, Any]] = {}

# MONGO_URL = "mongodb://root:cvrlkiryo,%5E@10.104.0.6:27017/"
DATABASE_NAME = "your_database"

earthly_data = {
    "Earthly Branch": ["Zi (子)", "Chou (丑)", "Yin (寅)", "Mao (卯)", "Chen (辰)", 
                        "Si (巳)", "Wu (午)", "Wei (未)", "Shen (申)", "You (酉)", 
                        "Xu (戌)", "Hai (亥)"],
    "Element": ["Water", "Earth", "Wood", "Wood", "Earth", 
                     "Fire", "Fire", "Earth", "Metal", "Metal", 
                     "Earth", "Water"],
    "Hidden Elements": ["None", "Metal, Water", "Fire, Earth", "None", "Wood, Water",
                         "Metal, Earth", "Earth", "Wood, Fire", "Water, Earth", "None",
                         "Fire, Metal", "Wood"],
    "Polarity": ["Yang", "Yin", "Yang", "Yin", "Yang",
                 "Yin", "Yang", "Yin", "Yang", "Yin",
                 "Yang", "Yin"],
    "Animal": ["Rat", "Ox", "Tiger", "Rabbit", "Dragon", 
                "Snake", "Horse", "Goat", "Monkey", "Rooster", 
                "Dog", "Pig"]
}

# Heavenly Stems data with elements and polarity
heavenly_data = {
    "Heavenly Stem": ["Jia (甲)", "Yi (乙)", "Bing (丙)", "Ding (丁)", "Wu (戊)", 
                       "Ji (己)", "Geng (庚)", "Xin (辛)", "Ren (壬)", "Gui (癸)"],
    "Element": ["Wood", "Wood", "Fire", "Fire", "Earth", 
                "Earth", "Metal", "Metal", "Water", "Water"],
    "Polarity": ["Yang", "Yin", "Yang", "Yin", "Yang",
                 "Yin", "Yang", "Yin", "Yang", "Yin"]
}

hidden_stems = {
    'Zi (子)': ['Gui (癸)'],
    'Chou (丑)': ['Ji (己)', 'Gui (癸)', 'Xin (辛)'],
    'Yin (寅)': ['Jia (甲)', 'Bing (丙)', 'Wu (戊)'],
    'Mao (卯)': ['Yi (乙)'],
    'Chen (辰)': ['Wu (戊)', 'Yi (乙)', 'Gui (癸)'],
    'Si (巳)': ['Bing (丙)', 'Wu (戊)', 'Geng (庚)'],
    'Wu (午)': ['Ding (丁)', 'Ji (己)'],
    'Wei (未)': ['Ji (己)', 'Ding (丁)', 'Yi (乙)'],
    'Shen (申)': ['Geng (庚)', 'Ren (壬)', 'Wu (戊)'],
    'You (酉)': ['Xin (辛)'],
    'Xu (戌)': ['Wu (戊)', 'Xin (辛)', 'Ding (丁)'],
    'Hai (亥)': ['Ren (壬)', 'Jia (甲)']
}

df_earthly = pd.DataFrame(earthly_data)
df_heavenly = pd.DataFrame(heavenly_data)

# df_element
headers = ["Self Element", "Influence Element", "Wealth Element", "Resource Element", "Output Element", "Companion Element"]
data = [
    ["Wood", "Metal", "Earth", "Water", "Fire", "Wood"],
    ["Water", "Earth", "Fire", "Metal", "Wood", "Water"],
    ["Fire", "Water", "Metal", "Wood", "Earth", "Fire"],
    ["Metal", "Fire", "Wood", "Earth", "Water", "Metal"],
    ["Earth", "Wood", "Water", "Fire", "Metal", "Earth"]
]
df_element = pd.DataFrame(data, columns=headers)

# df_variant
headers = ["Element", "Yang Variant", "Yin Variant"]
data = [
    ["Wood", "Jia Wood", "Yi Wood"],
    ["Fire", "Bing Fire", "Ding Fire"],
    ["Earth", "Wu Earth", "Ji Earth"],
    ["Metal", "Geng Metal", "Xin Metal"],
    ["Water", "Ren Water", "Gui Water"]
]
df_variant = pd.DataFrame(data, columns=headers)

five_factor_10gods = {
    'Output Element' : ['EG','HO'],
    'Wealth Element' : ['IW','DW'],
    'Influence Element' : ['7K','DO'],
    'Resource Element' : ['IR','DR'],
    'Companion Element' : ['F','RW']
}

heavenly_stems = list(df_heavenly['Heavenly Stem'])
earthly_branches = list(df_earthly['Earthly Branch'])
reference_date = datetime(1900, 1, 31)  # 📌 1900-01-31 is Jia Chen (甲辰)

class BaziInput(BaseModel):
    date_input: str  # Format: YYYY-MM-DD
    time_input: str = None  # Optional, default is noon if not provided
    sex: str  # 'male' or 'female'

def normalize_keys_to_snake_case(data):
    def to_snake_case(s):
        s = s.replace(" ", "_")
        s = re.sub(r'(?<=[a-z0-9])([A-Z])', r'_\1', s)
        s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s)
        s = re.sub(r'[^a-zA-Z0-9_]', '_', s)
        return s.lower()

    if isinstance(data, dict):
        return {to_snake_case(str(k)): normalize_keys_to_snake_case(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [normalize_keys_to_snake_case(item) for item in data]
    else:
        return data
    
def get_today():
    tz = pytz.timezone('Asia/Bangkok')
    now_thailand = datetime.now(tz)
    today_str = now_thailand.strftime('%Y-%m-%d')

    return today_str

def getDatail4Pillar(fp):
    def load_profiles(collection_name):
        client = MongoClient(MONGO_URL)
        db = client[DATABASE_NAME]
        collection = db[collection_name]
        
        collection = db[collection_name]
        profiles = list(collection.find({}))
        return profiles

    def find_profile(profiles, field, keyword):
        for profile in profiles:
            if keyword == str(profile.get(field, "")):
                return profile
        return None

    def format_thai_date(date_obj):
        thai_months = [
            "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
            "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
        ]
        return f"{date_obj.year}-{date_obj.month:02d}-{date_obj.day:02d}"

    def handle_daymaster(selected):
        profiles = load_profiles("daymaster_profiles")
        # print('profiles',profiles)
        profile = find_profile(profiles, "day_master", selected)

        if profile:
            result = {
                "status": "success",
                "selected": selected,
                "characteristics": profile.get("characteristics", "-"),
                "summary": profiles[0]['summary'],
                "strengths": profile.get("strengths", []),
                "weaknesses": profile.get("weaknesses", []),
                "advice_for_balance": profile.get("advice_for_balance", []),
                "charm": profile.get("charm", "-")
            }
        else:
            result = {
                "status": "not_found",
                "selected": selected,
                "message": "❌ ไม่พบข้อมูล"
            }

        return result

    def handle_zodiac(selected):
        profiles = load_profiles("zodiac_profiles")
        profile = find_profile(profiles, "zodiac", selected)

        if profile:
            result = {
                "status": "success",
                "selected": selected,
                "characteristics": profile.get("characteristics", "-"),
                "summary" : profiles[0]['summary'],
                "strengths": profile.get("strengths", []),
                "weaknesses": profile.get("weaknesses", []),
                "charm": profile.get("charm", "-"),
                "advice_for_balance": profile.get("advice_for_balance", []),
                "zodiac_relations": profile.get("zodiac_relations", [])
            }
        else:
            result = {
                "status": "not_found",
                "selected": selected,
                "message": "❌ ไม่พบข้อมูล"
            }

        return result
    
    def DayMaster(fp):
        def map_heavenly_stem_to_thai_description(stem):
            stem_properties = {
                "Jia": ("Wood", "Yang"),
                "Yi": ("Wood", "Yin"),
                "Bing": ("Fire", "Yang"),
                "Ding": ("Fire", "Yin"),
                "Wu": ("Earth", "Yang"),
                "Ji": ("Earth", "Yin"),
                "Geng": ("Metal", "Yang"),
                "Xin": ("Metal", "Yin"),
                "Ren": ("Water", "Yang"),
                "Gui": ("Water", "Yin"),
            }

            mapping = {
                ("Earth", "Yang"): '"ดินหยาง" หรือ “ภูเขาใหญ่”',
                ("Earth", "Yin"): '"ดินหยิน" หรือ “ผืนดิน”',
                ("Metal", "Yang"): '"ทองหยาง" หรือ “เหล็กกล้า”',
                ("Metal", "Yin"): '"ทองหยิน" หรือ “เครื่องประดับ”',
                ("Water", "Yang"): '"น้ำหยาง" หรือ “แม่น้ำใหญ่”',
                ("Water", "Yin"): '"น้ำหยิน" หรือ “หยดน้ำ”',
                ("Fire", "Yang"): '"ไฟหยาง" หรือ “พระอาทิตย์”',
                ("Fire", "Yin"): '"ไฟหยิน" หรือ “แสงเทียน”',
                ("Wood", "Yang"): '"ไม้หยาง" หรือ “ต้นไม้ใหญ่”',
                ("Wood", "Yin"): '"ไม้หยิน" หรือ “เถาวัลย์”',
            }

            if stem in stem_properties:
                element_type, polarity = stem_properties[stem]
                return mapping.get((element_type, polarity)),element_type, polarity
            else:
                return "ไม่พบข้อมูล Heavenly Stem ที่ระบุ",None,None

        x = fp['four_pillars']['Day']['stem']
        dm,element_type, polarity = map_heavenly_stem_to_thai_description(x.split()[0])
        s = handle_daymaster(dm)

        return s,element_type, polarity

    def Zodiac(fp):
        def map_zodiac_chinese_to_thai(chinese_code):
            zodiac_list = [
                '"กระต่าย" (Mao)', '"งู" (Si)', '"มังกร" (Chen)', '"ม้า" (Wu)',
                '"ลิง" (Shen)', '"วัว" (Chou)', '"สุนัข" (Xu)', '"หนู" (Zi)',
                '"หมา" (Xu)', '"หมู" (Hai)', '"เสือ" (Yin)', '"แพะ" (Wei)', '"ไก่" (You)'
            ]

            for item in zodiac_list:
                if f"({chinese_code})" in item:
                    return item

            return None

        chinese_code = fp['four_pillars']['Day']['branch'].split()[0]
        mm = map_zodiac_chinese_to_thai(chinese_code)

        return handle_zodiac(mm)
    
    s,element_type, polarity = DayMaster(fp)
    
    d = {
        'element_type' : element_type,
        'polarity' : polarity,
        'animal' : fp['four_pillars']['Day']['branch_animal'],
        'day_master' : s,
        'zodiac' : Zodiac(fp)
    }
    
    return d


def Api1FourPillarLuckPillar(date_input,time_inputs,sex):
    debug_print('cvvvv')
    results = AllBaziCalulate(date_input,time_inputs,sex)
    results['detail'] = getDatail4Pillar(results)

    debug_print('results',results)

    return results


def AllBaziCalulate(date_input,time_inputs,sex):
    def get_heavenly_earthly_year(lunar_year):
        """ Compute the Heavenly Stem and Earthly Branch for a given lunar year. """
        stem_index = (lunar_year - 4) % 10
        branch_index = (lunar_year - 4) % 12
        return heavenly_stems[stem_index], earthly_branches[branch_index]

    def get_heavenly_earthly_month(lunar_year, lunar_month, lunar_day):
        """ Compute the Heavenly Stem and Earthly Branch for a given lunar month. """
        branch_index = (lunar_month + 1) % 12  
        year_stem_index = (lunar_year - 4) % 10 
        stem_index = (year_stem_index * 2 + lunar_month) % 10 - 9


        td = find_transition_date(int(date_input.split('-')[0]),int(date_input.split('-')[1]))

        gregorian_date = datetime.strptime(td, "%Y-%m-%d")
        gregorian_date = gregorian_date + timedelta(hours=dt)
        td_lunar_date = lunarcalendar.Converter.Solar2Lunar(gregorian_date)

        if td_lunar_date.day > 15 or td_lunar_date.isleap:
            stem_index += 1
            branch_index += 1
            if stem_index > len(heavenly_stems) - 1:
                stem_index = 0
            if branch_index > len(earthly_branches) - 1:
                branch_index = 0

        return heavenly_stems[stem_index], earthly_branches[branch_index]

    def get_heavenly_earthly_day(gregorian_date):
        """ Compute the Heavenly Stem and Earthly Branch for a given day. """
        days_since_reference = (gregorian_date - reference_date).days
        stem_index = (days_since_reference) % 10  # 📌 Offset by +6 (Jia Chen, 甲辰)
        branch_index = (days_since_reference + 4) % 12  # 📌 Offset by +4
        return heavenly_stems[stem_index], earthly_branches[branch_index]

    def get_heavenly_earthly_hour(input_time,day_stem):
        def look_hr_table(day_stem,branch,idx):
            def lx(x):
                start_index = heavenly_stems.index(x)
                cyclic_list = [heavenly_stems[(start_index + i) % len(heavenly_stems)] for i in range(13)]
                cyclic_list = [cyclic_list[-1]] + cyclic_list[:-1]

                return cyclic_list

            X = []
            for x in ["Jia (甲)",'Bing (丙)','Wu (戊)','Geng (庚)','Ren (壬)']:
                X.append(lx(x))

            if day_stem in ['Jia (甲)','Ji (己)']:
                z = X[0]
            elif day_stem in ['Yi (乙)','Geng (庚)']:
                z = X[1]
            elif day_stem in ['Bing (丙)','Xin (辛)']:
                z = X[2]
            elif day_stem in ['Ding (丁)','Ren (壬)']:
                z = X[3]
            elif day_stem in ['Wu (戊)','Gui (癸)']:
                z = X[4]

            return z[idx],branch

        def get_earthly_branch_from_hour(input_time):
            """Determine the Earthly Branch (Shichen) from a given hour in 24-hour format."""
            hour = int(input_time.split(":")[0])
            shichen_table = {
                (0, 0.9): earthly_branches[0],
                (23, 24): earthly_branches[0],
                (1, 2): earthly_branches[1],
                (3, 4): earthly_branches[2],
                (5, 6): earthly_branches[3],
                (7, 8): earthly_branches[4],
                (9, 10): earthly_branches[5],
                (11, 12): earthly_branches[6],
                (13, 14): earthly_branches[7],
                (15, 16): earthly_branches[8],
                (17, 18): earthly_branches[9],
                (19, 20): earthly_branches[10],
                (21, 22): earthly_branches[11]
                
            }
            for (start, end), branch in shichen_table.items():
                if start <= hour <= end:
                    return branch
            return "Unknown"

        branch = get_earthly_branch_from_hour(input_time)
        if branch == "Ye Zi":
            idx = 0
        else:
            idx = earthly_branches.index(branch)+1

        return look_hr_table(day_stem,branch,idx)

    def get_stem_branch_for_date(date_str, time_input, dt):
        """ Convert a Gregorian date to a Lunar date and return the Heavenly Stem and Earthly Branch. """
        gregorian_date = datetime.strptime(date_str, "%Y-%m-%d")
        gregorian_date = gregorian_date + timedelta(hours=dt)
        
        lunar_date = lunarcalendar.Converter.Solar2Lunar(gregorian_date)
        year_stem, year_branch = get_heavenly_earthly_year(lunar_date.year)
        month_stem, month_branch = get_heavenly_earthly_month(lunar_date.year, lunar_date.month, lunar_date.day)
        day_stem, day_branch = get_heavenly_earthly_day(gregorian_date)
        hour_stem, hour_branch = get_heavenly_earthly_hour(time_input,day_stem)
        
        return {
            "Year" : { "stem" : year_stem , "branch" : year_branch },
            "Month" : { "stem" : month_stem , "branch" : month_branch },
            "Day" : { "stem" : day_stem , "branch" : day_branch },
            "Hour" : { "stem" : hour_stem , "branch" : hour_branch },
            "LunarDate": f"{lunar_date.year}-{lunar_date.month}-{lunar_date.day}" 
        }

    def find_luck_pillars(sex,stem_branch):
        def is_fw(sex,stem_branch_year):
            if heavenly_stems.index(stem_branch_year) % 2 == 0:
                yy = 'yang'
            else:
                yy = 'yin'

            if yy == 'yang' and sex == 'male' or yy == 'yin' and sex == 'female':
                fw = True
            else:
                fw = False
            return fw
        
        stem_branch_year = stem_branch['Year']['stem']
        is_forward = is_fw(sex,stem_branch_year)
        stem_branch_day = stem_branch['Month']

        start_index = heavenly_stems.index(stem_branch_day['stem'])
        start_branch_index = earthly_branches.index(stem_branch_day['branch'])

        if is_forward:
            debug_print('fw')
            luck_pillars_heavenly_stems = [heavenly_stems[(start_index + i) % len(heavenly_stems)] for i in range(10)]
            luck_pillars_earthly_branches = [earthly_branches[(start_branch_index + i) % len(earthly_branches)] for i in range(10)]
        
            luck_pillars_heavenly_stems.reverse()
            luck_pillars_heavenly_stems = luck_pillars_heavenly_stems[:-1]
            # luck_pillars_heavenly_stems.reverse()
            luck_pillars_earthly_branches.reverse() 
            luck_pillars_earthly_branches = luck_pillars_earthly_branches[:-1]
            # luck_pillars_heavenly_stems.reverse()
            # luck_pillars_heavenly_stems = luck_pillars_heavenly_stems[1:]
            # luck_pillars_earthly_branches = luck_pillars_earthly_branches[1:]

        else:
            debug_print('bw')
            luck_pillars_heavenly_stems = [heavenly_stems[(start_index - i) % len(heavenly_stems)] for i in range(11)]
            luck_pillars_earthly_branches = [earthly_branches[(start_branch_index - i) % len(earthly_branches)] for i in range(11)]

            luck_pillars_heavenly_stems.reverse()
            luck_pillars_heavenly_stems = luck_pillars_heavenly_stems[:-1]
            luck_pillars_earthly_branches.reverse() 
            luck_pillars_earthly_branches = luck_pillars_earthly_branches[:-1]

            luck_pillars_heavenly_stems = luck_pillars_heavenly_stems[:-1]
            luck_pillars_earthly_branches = luck_pillars_earthly_branches[:-1]
        
        start_day = find_start_day_lp(date_input,is_forward)

        return luck_pillars_heavenly_stems,luck_pillars_earthly_branches,start_day

    def get_polarity_element(stem):
        z = df_heavenly[df_heavenly['Heavenly Stem']==stem]
        z = dict(z.iloc[0])
        
        return {
            'stem' : stem,
            'stem_element' : z['Element']
        }

    def update_stem_branch_detail(stem_branch):
        stem_branchs = stem_branch.copy()
        for k in stem_branch:
            z = {}
            if k != 'LunarDate':
                for kk in stem_branch[k]:
                    if kk == 'stem':
                        z.update(get_polarity_element(stem_branch[k][kk]))
                    if kk == 'branch':
                        z['branch'] = stem_branch[k][kk]
                        z['branch_animal'] = df_earthly[df_earthly['Earthly Branch'] == z['branch']].iloc[0]['Animal']
                        z['branch_element'] = df_earthly[df_earthly['Earthly Branch'] == z['branch']].iloc[0]['Element']
                        z['hidden_stem'] = hidden_stems[z['branch']]
                        z['polarity'] = df_earthly[df_earthly['Earthly Branch'] == z['branch']].iloc[0]['Polarity']                 
                stem_branchs[k] = z

        return stem_branchs

    def find_10g(stem_branch,stem):
        hss = stem.split()[0]
        
        hs = stem_branch['Day']['stem']
        df_day = df_heavenly[df_heavenly['Heavenly Stem']==hs]
        ele = df_day.iloc[0]['Element']
        
        df_element_day = df_element[df_element['Self Element']==ele].reset_index(drop=True).T
        df_element_day = df_element_day.rename(columns={0: 'Element'})

        Yin = []
        Yang = []
        for index, row in df_element_day.iterrows():
            yin = df_variant[df_variant['Element']==row['Element']]['Yin Variant'].iloc[0]
            yang = df_variant[df_variant['Element']==row['Element']]['Yang Variant'].iloc[0]
            Yin.append(yin)
            Yang.append(yang)
        df_element_day['Yin'] = Yin
        df_element_day['Yang'] = Yang
        
        df_element_day = df_element_day.drop(index='Self Element')
        df_element_day[['Yin_stem', 'Yin_element']] = df_element_day['Yin'].str.split(' ', expand=True)
        df_element_day[['Yang_stem', 'Yang_element']] = df_element_day['Yang'].str.split(' ', expand=True)
        
        try:
            z = df_element_day[df_element_day['Yin_stem']==hss].index[0]
            yy = 'Yin'
        except:
            z = df_element_day[df_element_day['Yang_stem']==hss].index[0]
            yy = 'Yang'
        tg = five_factor_10gods[z]
        
        zz = df_heavenly[df_heavenly['Heavenly Stem']==stem]
        zz = dict(zz.iloc[0])

        if zz['Polarity'] == 'Yin':
            if stem_branch['Day']['polarity'] == 'Yang':
                zz = tg[1]
            else:
                zz = tg[0]
        else:
            if stem_branch['Day']['polarity'] == 'Yang':
                zz = tg[0]
            else:
                zz = tg[1]
            
        return zz

    def update_10g(stem_branch):
        for k in stem_branch:
            if k != 'LunarDate':
                stem_branch[k]['stem_10g'] = find_10g(stem_branch,stem_branch[k]['stem'])

                G = []
                E = []
                for kk in stem_branch[k]['hidden_stem']:
                    G.append(find_10g(stem_branch,kk))
                    E.append(stem_to_element(kk))
                stem_branch[k]['hidden_stem_10g'] = G
                stem_branch[k]['hidden_stem_element'] = E
        return stem_branch

    def update_lp_10g(lp):
        lps = lp.copy()
        for k in lp.keys():
            lps[k]['stem_10g'] = find_10g(stem_branch,lp[k]['stem'])

            z = []
            E = []
            for kk in lp[k]['hidden_stem']:
                z.append(find_10g(stem_branch,kk))
                E.append(stem_to_element(kk))
            lps[k]['hidden_stem_10g'] = z
            lps[k]['hidden_stem_element'] = E

        return lps

    def stem_to_element(stem):
        z = df_heavenly[df_heavenly['Heavenly Stem']==stem]
        z = dict(z.iloc[0])
        s = ''
        if z['Polarity'] == 'Yin':
            s += '-'
        else:
            s += '+'
        s += z['Element']
        return s

    def find_percen_ele(stem_branch):
        E = []
        for p in ['Year','Month','Day','Hour']:
            E += [stem_branch[p]['stem_element']]
            E += [stem_branch[p]['branch_element']]
            E += [x.replace('-','').replace('+','') for x in stem_branch[p]['hidden_stem_element']]
        count_result = dict(Counter(E))
        total_elements = len(E)
        proportion_result = {key: value / total_elements for key, value in count_result.items()}

        s = {'Wood', 'Water', 'Metal', 'Earth', 'Fire'} - set(proportion_result.keys())
        if s:
            for ss in s:
                proportion_result[ss] = 0
        return proportion_result

    # transition day -----
    def find_transition_date(year,month):
        df = pd.read_csv("MonthChangeData.csv")
        y_t,m_t,d_t = year,month,int(df[df['year']==year].iloc[0][f'month_{month}'])
        
        date_str = f"{y_t}-{m_t}-{d_t}"
        formatted_date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
        return formatted_date

    def find_diff_days(date_input,date_transition):
        date1 = datetime.strptime(date_input, "%Y-%m-%d")
        date2 = datetime.strptime(date_transition, "%Y-%m-%d")        
        difference_days = (date2 - date1).days + 1 
        
        return difference_days
        
    def find_start_day_lp(date_input,is_fw):

        [y,m,d] = [int(x) for x in date_input.split('-')]

        if is_fw: # b) If the Forward cycle is being used, then count the number of days between the person’s Day of Birth and the next monthly transition point.
            m_t = m + 1
            if m_t == 13:
                m_t = 1
                y += 1

            date_transition = find_transition_date(y,m_t)
            diff_day = find_diff_days(date_input,date_transition)

        else:  # a Reverse cycle is used, then count the number of days between the person’s Day of Birth and the nearest monthly transition point
            date_t = find_transition_date(y,m)
            if int(date_input.split('-')[-1]) > int(date_t.split('-')[-1]):
                m_t = m
            else:
                m_t = m - 1

            if m_t == 0:
                m_t = 12
                y -= 1

            date_transition = find_transition_date(y,m_t)
            diff_day = find_diff_days(date_transition,date_input)

        start_day = int(diff_day/3)%10
        
        if start_day == 0:
            start_day = 9
        return start_day

    if not time_inputs:
        time_input = '12:00'
    else:
        time_input = time_inputs

    # 4 pillar and 10 gods
    dt = 0
    stem_branch = get_stem_branch_for_date(date_input,time_input,dt)
    stem_branch = update_stem_branch_detail(stem_branch)
    stem_branch = update_10g(stem_branch)

    # luckpillar, 10 gods and age-ranges
    lp = find_luck_pillars(sex,stem_branch)
    start_age = lp[-1]

    numbers = [start_age + i * 10 for i in range(9)]
    ranges = [f"{numbers[i]}-{numbers[i+1]}" for i in range(len(numbers) - 1)]

    ranges = [f"{numbers[i]}-{numbers[i+1]}" for i in range(len(numbers)-1)]
    ranges.append(f"{numbers[-1]}-{numbers[-1] + (numbers[1] - numbers[0])}")
    ranges.reverse()

    lp = {
        f'age_{ranges[i]}': {'stem': lp[0][i], 'branch': lp[1][i]} 
        for i in range(len(lp[0]))
    }
    lp = update_stem_branch_detail(lp)
    lp = update_lp_10g(lp)
    

    # percen_elements
    pe = find_percen_ele(stem_branch)

    input_data = {
        'date_input' : date_input,
        'time_input' : time_inputs,
        'sex' : sex
    }

    luck_pillars_list = [
    {"age": key.split("_")[1], **value}
    for key, value in lp.items()
    ]

    results = {
        'input_data' : input_data ,
        'four_pillars' : stem_branch,
        'luck_pillars' : luck_pillars_list,
        'percen_elements' : pe
    }

    if not time_inputs:
        results['four_pillars']['Hour'] = None

    return results

# api2 -----------------------------------------------------------------------
def Api2CurrentYearMonthEnergy(current_date=get_today()):

    # Convert to datetime object
    current_date = datetime.strptime(current_date, "%Y-%m-%d").date()

    # start api2
    data = {}

    # find current date
    results  = AllBaziCalulate(str(current_date),"12:00",'male')
    current_lunar_date = results['four_pillars']['LunarDate']
    current_anual_energy = results['four_pillars']['Year']

    # find year energy
    data['current_anual_energy'] = current_anual_energy

    # find 12 months energy
    if current_date > date(current_date.year, 2, 15):
        current_year_ref = current_date.year
    else:
        current_year_ref = current_date.year - 1
        
    data['current_year_ref'] = current_year_ref
    data['current_date'] = str(current_date)

    debug_print('current_year_ref',current_year_ref)
    ly = list_month_energy(current_year_ref)
    data['monthly_enery_of_current_year']  = ly

    debug_print('data',data)

    return data

def list_month_energy(current_enery_year):
    months_energy = {}
    for m in range(1,13):
        solar_date_str = f"{current_enery_year}-{m}-15"
        results  = AllBaziCalulate(solar_date_str,"12:00",'male')
        results['four_pillars'].pop('Hour')

        results['four_pillars']['Date'] = solar_date_str
        months_energy[m] = results['four_pillars']['Month']
        
    return months_energy

# api3 -----------------------------------------------------------------------
def Api3FiveYearEnergyForecast(current_date=get_today()):

    def find_year_energy(current_date):
        current_date = datetime.strptime(current_date, "%Y-%m-%d").date()
        results  = AllBaziCalulate(str(current_date),"12:00",'male')
        current_anual_energy = results['four_pillars']['Year']

        return current_anual_energy

    data = {}
    for i in range(5):

        current_anual_energy = find_year_energy(current_date)
        current_date = datetime.strptime(current_date, "%Y-%m-%d").date()

        data[f'{current_date.year}'] = current_anual_energy

        current_date = current_date + timedelta(days=365)
        current_date = current_date.strftime('%Y-%m-%d')

    return data

# api4 -----------------------------------------------------------------------
def Api4NextWeekDailyEnergy(date_input=None):
    if date_input is None:
        date_input = get_today()   # จะถูก evaluate ทุกครั้งที่เรียกใช้

    start_date = datetime.strptime(date_input, "%Y-%m-%d")
    days_ahead = 7 - start_date.weekday()  # 0 = Monday, ..., 6 = Sunday
    next_monday = start_date + timedelta(days=days_ahead)
    next_week = [(next_monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    week_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    results_nextweek = {'date_today': date_input}
    
    for i, date_input in enumerate(next_week):
        time_input = "07:09"
        sex = 'male'
        result = AllBaziCalulate(date_input, time_input, sex)
        
        if i == 0:
            results_nextweek['Month'] = result['four_pillars']['Month']
            results_nextweek['Year'] = result['four_pillars']['Year']
            
        data = result['four_pillars']['Day']
        data['day'] = week_days[i]
        results_nextweek[date_input.replace("-", "_")] = data   # ใช้รูปแบบ key เดียวกับ output

    return results_nextweek
# def Api4NextWeekDailyEnergy(date_input=get_today()):

#     # Get list of dates from next Monday to next Sunday
#     start_date = datetime.strptime(date_input, "%Y-%m-%d")
#     days_ahead = 7 - start_date.weekday()  # 0 = Monday, ..., 6 = Sunday
#     next_monday = start_date + timedelta(days=days_ahead)
#     next_week = [(next_monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

#     week_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

#     results_nextweek = {}
#     results_nextweek['date_today'] = date_input
    
#     for i,date_input in enumerate(next_week):
#         time_input = "07:09"
#         sex = 'male'
#         result = AllBaziCalulate(date_input,time_input,sex)
        
#         if i == 0:
#             data = result['four_pillars']['Month']
            
#             # filtered_data = {k: data[k] for k in ['stem','branch'] if k in data}
#             # results_nextweek['Month'] = filtered_data
#             results_nextweek['Month'] = data
            
#             data = result['four_pillars']['Year']

#             # filtered_data = {k: data[k] for k in ['stem','branch'] if k in data}
#             # results_nextweek['Year'] = filtered_data
#             results_nextweek['Year'] = data
            
#         data = result['four_pillars']['Day']

#         # filtered_data = {k: data[k] for k in ['stem','branch'] if k in data}
#         # results_nextweek[date_input] = filtered_data
#         results_nextweek[date_input] = data

#         results_nextweek[date_input]['day'] = week_days[i]
        
#     return results_nextweek

# api5 -----------------------------------------------------------------------
def Api5StarPredict(birth_date,target_date=get_today()):

    def star_detail(star):
        df = pd.read_csv('StarDetail.csv')  
        df = df[df['star']==star]

        dict_list = df.to_dict(orient="records")

        return dict_list[0]

    def findisStar(star):
        if star == 'Nobleman':
            df_filtered = df[df['star']==star]
            df_filtered = df_filtered[df_filtered['fourpillar_day_stem']==fourpillar_day_stem]
            df_filtered = df_filtered[df_filtered['day_branch']==day_branch]
            return df_filtered

        elif star == 'Peach blossom':
            df_filtered = df[df['star']==star]
            df_filtered = df_filtered[df_filtered['fourpillar_day_branch']==fourpillar_day_branch]
            df_filtered = df_filtered[df_filtered['day_branch']==day_branch]

            if not df_filtered.shape[0]:
                df_filtered = df[df['star']==star]
                df_filtered = df_filtered[df_filtered['fourpillar_year_branch']==fourpillar_year_branch]
                df_filtered = df_filtered[df_filtered['day_branch']==day_branch]
            return df_filtered

        elif star == 'Heavenly virtue':
            df_filtered = df[df['star']==star]
            df_filtered = df_filtered[df_filtered['fourpillar_month_branch']==fourpillar_month_branch]
            df_filtered = df_filtered[df_filtered['day_stem']==day_stem]
            return df_filtered

        elif star == 'Fortune virtue':
            df_filtered = df[df['star']==star]
            df_filtered = df_filtered[df_filtered['fourpillar_year_branch']==fourpillar_year_branch]
            df_filtered = df_filtered[df_filtered['day_branch']==day_branch]
            return df_filtered

        elif star == 'Clash':
            df_filtered = df[df['star']==star]
            df_filtered = df_filtered[df_filtered['fourpillar_day_branch']==fourpillar_day_branch]
            df_filtered = df_filtered[df_filtered['day_branch']==day_branch]
            df_filtered

            if not df_filtered.shape[0]:
                df_filtered = df[df['star']==star]
                df_filtered = df_filtered[df_filtered['fourpillar_month_branch']==fourpillar_day_branch]
                df_filtered = df_filtered[df_filtered['day_branch']==day_branch]
            return df_filtered
        
    debug_print('target_date',target_date)
    target_day  = AllBaziCalulate(target_date,"12:00",'male')

    df = pd.read_csv('StarData.csv')
    # Capitalize strings only
    df = df.applymap(lambda x: x.capitalize() if isinstance(x, str) else x)
    
    fp  = AllBaziCalulate(str(birth_date),"12:00",'male')
    
    day_stem = target_day['four_pillars']['Day']['stem'].split()[0]
    day_branch = target_day['four_pillars']['Day']['branch'].split()[0]
    
    fp = fp['four_pillars']
    fourpillar_day_stem = fp['Day']['stem'].split()[0]
    fourpillar_day_branch = fp['Day']['branch'].split()[0]
    fourpillar_month_branch = fp['Month']['branch'].split()[0]
    fourpillar_year_branch = fp['Year']['branch'].split()[0]
    
    # df_combined = pd.concat([df1, df2], ignore_index=True)
    df_combined = []
    for star in ['Nobleman','Peach blossom','Heavenly virtue','Fortune virtue','Clash']:
        df_filtered = findisStar(star)
        df_combined.append(df_filtered)
        debug_print(star,df_filtered.shape)

    df_combined = pd.concat(df_combined, ignore_index=True)
    debug_print(df_combined)
#     return list(df_combined['star'].unique())

    S = {}
    for s in list(df_combined['star'].unique()):
        S[s] = star_detail(s)
    return S
    
# api6 -----------------------------------------------------------------------
def Api6GetDetailDate(formatted):
        def load_profiles(collection_name):
            client = MongoClient(MONGO_URL)

            db = client[DATABASE_NAME]
            collection = db[collection_name]
            
            profiles = list(collection.find({}))
            return profiles

        def find_profile(profiles, field, keyword):
            for profile in profiles:
                if keyword == str(profile.get(field, "")):
                    return profile
            return None

        profiles = load_profiles("calendar_profiles_2568")
        profile = find_profile(profiles, "date", formatted)

        if profile:
            result = {
                "status": "success",
                "date": formatted,
                "theme": profile.get("theme", "-"),
                "day_quote": profile.get("day_quote", "-"),
                "highlight_of_day": profile.get("highlight_of_day", "-"),
                "power_of_day": profile.get("power_of_day", "-"),
                "seasonal_effect": profile.get("seasonal_effect", "-"),
                "lucky_color": profile.get("lucky_color", []),
                "things_to_do": profile.get("things_to_do", []),
                "things_to_avoid": profile.get("things_to_avoid", []),
                "zodiac_relations": profile.get("zodiac_relations", [])
            }
        else:
            result = {
                "status": "not_found",
                "date": formatted,
                "message": "❌ ไม่พบข้อมูลในวันนั้น"
            }

        return result


# calendar general api -----------
def get_general_calendar(year, month):
    def load_calendar_profile_month(year, month):
        # COLLECTION_NAME = "calendar_profiles_2568"
        COLLECTION_NAME = f"calendar_profiles_{year+543}"
        client = MongoClient(MONGO_URL)
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]

        start_str = datetime(year, month, 1).strftime("%Y-%m-%d")
        end_str = datetime(year + 1, 1, 1).strftime("%Y-%m-%d") if month == 12 else datetime(year, month + 1, 1).strftime("%Y-%m-%d")

        results = list(collection.find({
            "date": {"$gte": start_str, "$lt": end_str}
        }))
        df = pd.DataFrame(results)
        if "_id" in df.columns:
            df.drop(columns=["_id"], inplace=True)
        return df.astype(str)

    def load_calendar_holiday_month(year, month):
        # COLLECTION_NAME = "calendar_holidays_until2055_2"
        COLLECTION_NAME = "calendar_holidays_until2025_2"
        client = MongoClient(MONGO_URL)
        db = client[DATABASE_NAME]
        collection = db[COLLECTION_NAME]

        start = datetime(year, month, 1)
        end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

        results = list(collection.find({
            "date": {"$gte": start, "$lt": end}
        }))
        df = pd.DataFrame(results)
        if "_id" in df.columns:
            df.drop(columns=["_id"], inplace=True)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df.astype(str)
    
    try:
        df1 = load_calendar_profile_month(year, month)
        # ✅ แก้ปัญหาค่า NaN / inf
        df1 = df1.replace([float("inf"), float("-inf")], pd.NA)
        df1 = df1.fillna("")  # เปลี่ยน NaN เป็น string ว่าง
        df1 = df1.astype(str)  # แปลงทุกค่าเป็น string
        df1 = df1.set_index("date").to_dict(orient="index")
    except:
        df1 = None

    try:
        df2 = load_calendar_holiday_month(year, month)
        df2 = df2.replace([float("inf"), float("-inf")], pd.NA)
        df2 = df2.fillna("")  # เปลี่ยน NaN เป็น string ว่าง
        df2 = df2.astype(str)  # แปลงทุกค่าเป็น string
        df2 = df2.drop_duplicates(subset=["date"])
        df2 = df2.set_index("date").to_dict(orient="index")

    except:
        df2 = None
        
    df_dict = {
        "profile" : df1,
        "holiday" : df2
    }

    return df_dict

def format_subcontent(data):
    content = []
    for i in data:
        header, detail = i.split(':')[0].strip(),i.split(':')[1].strip()
        content.append({"header" : header, "detail":detail})
    D = {
        "type" : "subContent",
        "content" : content
    }
    return D

def format_text(data):
    D = {
        "type" : "text",
        "content" : data.replace('"','').replace('\\','').strip()
    }
    return D

def clean_text(data):
    return data.replace('"','').replace('\\','').strip()

def format_bullet(data):
    d = { 
        "type" : "bullet",
        "content" : data
    }
    return d

def format_number(data):
    d = { 
        "type" : "bullet",
        "content" : data
    }
    return d
    
def format_2section(text):
    # text = "['สีมงคล: สีเขียว, สีส้ม, สีเหลือง – เสริมความหนักแน่นและความมั่นคง', 'สีที่ควรหลีกเลี่ยง: สีดำ, สีแดงสด – ลดพลังแห่งสมดุล']"
    items = ast.literal_eval(text)
    
    result = {
        "type": "2section",
        "mode": "color",
        "content": []
    }
    
    for item in items:
        # แยกหัวข้อกับเนื้อหา
        head_part, rest = item.split(":", 1)
        icons_part, detail_part = rest.split("–", 1)
    
        # สร้าง object
        section = {
            "head": head_part.strip(),
            "icon": [i.strip() for i in icons_part.split(",")],
            "detail": detail_part.strip()
        }
        result["content"].append(section)

    return result
    
    
def fomat_basic_info(basic_info):
    
    day_master = basic_info['detail']['day_master']
    zodiac = basic_info['detail']['zodiac']

    D = {}
    D['characteristic'] = day_master['characteristics']
    D['general'] = format_text(day_master['summary'])
    D['strenght'] = format_subcontent(day_master['strengths'])
    D['weaknesses'] = format_subcontent(day_master['weaknesses'])
    D['recommend'] = format_subcontent(day_master['advice_for_balance'])
    D['attractive'] = format_text(day_master['charm'])

    Z = {}
    Z['characteristic'] = zodiac['characteristics']
    Z['general'] = format_text(zodiac['summary'])
    Z['strong'] = format_subcontent(zodiac['strengths'])
    Z['weakness'] = format_subcontent(zodiac['weaknesses'])
    Z['recommend'] = format_subcontent(zodiac['advice_for_balance'])
    Z['attractive'] = format_text(zodiac['charm'])
    Z['relations'] = format_2section_relations(zodiac['zodiac_relations'])

    basic_info['detail']['day_master'] = D
    basic_info['detail']['zodiac'] = Z


    return basic_info


def format_2section_color(text):
    thai_colors = [
        'สีแดง', 'สีแดงอ่อน', 'สีแดงเข้ม', 'สีแดงสด',
        'สีชมพู', 'สีชมพูอ่อน', 'สีชมพูสด',
        'สีม่วง', 'สีม่วงเข้ม',
        'สีน้ำเงิน', 'สีฟ้า', 'สีฟ้าเข้ม', 'สีฟ้าอ่อน', 'สีฟ้าสดใส',
        'สีเขียว', 'สีเขียวอ่อน', 'สีเขียวเข้ม', 'สีเขียวสด',
        'สีส้ม', 'สีส้มอ่อน', 'สีส้มเข้ม', 'สีส้มสด',
        'สีเหลือง', 'สีเหลืองอ่อน', 'สีเหลืองเข้ม', 'สีเหลืองสด', 'สีเหลืองทอง',
        'สีทอง',
        'สีเทา', 'สีเทาเข้ม', 'สีเทาอ่อน',
        'สีขาว', 'สีดำ', 'สีดำเข้ม',
        'สีน้ำตาล', 'สีเงิน', 'สีครีม'
    ]
    
    english_colors = [
        'red', 'light_red', 'dark_red', 'bright_red',
        'pink', 'light_pink', 'vivid_pink',
        'purple', 'dark_purple',
        'navy_blue', 'blue', 'dark_blue', 'light_blue', 'sky_blue',
        'green', 'light_green', 'dark_green', 'bright_green',
        'orange', 'light_orange', 'dark_orange', 'vivid_orange',
        'yellow', 'light_yellow', 'dark_yellow', 'bright_yellow', 'golden_yellow',
        'gold',
        'gray', 'dark_gray', 'light_gray',
        'white', 'black', 'dark_black',
        'brown', 'silver', 'cream'
    ]
    
    
    def color_thai_to_english(thai_color):
        mapping = dict(zip(thai_colors, english_colors))
        return mapping.get(thai_color, None)
    
    try:
        c = text.replace('"',' ').replace("["," ").replace("'"," ").replace("]"," ")

        c1,c2 = c.split('สีที่ควร')
        d1 = c1.split('–')[1].replace(',','').replace('"','').replace("'",'').strip()
        d2 = c2.split('–')[1].replace(',','').replace('"','').replace("'",'').strip()
        c1 = c1.split('–')[0].split(':')[1].split()
        c2 = c2.split('–')[0].split(':')[1].split()
        c1 = [x.strip().replace(',',"") for x in c1]
        c2 = [x.strip().replace(',',"") for x in c2]

        # c1 = [color_thai_to_english(x) for x in c1]
        # c2 = [color_thai_to_english(x) for x in c2]

        z = [{
            "header": "สีที่เหมาะกับคุณ",
            "icon": c1,
            "detail": d1
        },
        {
            "header": "สีที่ควรหลีกเลี่ยง",
            "icon": c2,
            "detail": d2
        }]

    except:
        random_colors = random.sample(english_colors, 5)
        z = [{
            "header": "สีที่เหมาะกับคุณ",
            "icon": random_colors[:3],
            "detail": "-"
        },
        {
            "header": "สีที่ควรหลีกเลี่ยง",
            "icon": random_colors[3:],
            "detail": "-"
        }]
        pass

    return z

def format_2section_zodiac_relations(c):
  
    try:
        c = c.replace('"',' ').replace("["," ").replace("'"," ").replace("]"," ")
        c1,c2 = c.split('ขัดแย้ง')
        d1 = c1.split('–')[1].replace(',','').replace('"','').replace("'",'').strip()
        d2 = c2.split('–')[1].replace(',','').replace('"','').replace("'",'').strip()
        c1 = c1.split('–')[0].split(':')[1].split()
        c2 = c2.split('–')[0].split(':')[1].split()
        c1 = [x.strip().replace(',',"") for x in c1]
        c2 = [x.strip().replace(',',"") for x in c2]

        cc1 = []
        for aa in c1:
            an = animal_thai_to_eng(aa)
            if an:
                cc1.append(an)

        cc2 = []
        for aa in c2:
            an = animal_thai_to_eng(aa)
            if an:
                cc2.append(an)
        
        z = [{
            "header": "ส่งเสริม",
            "icon": cc1,
            "content": d1
        },
        {
            "header": "ขัดแย้ง",
            "icon": cc2,
            "content": d2
        }]
    except:
        z = [{
            "header": "ส่งเสริม",
            "icon": "-",
            "content": "-"
        },
        {
            "header": "ขัดแย้ง",
            "icon": "-",
            "content": "-"
        }]
    return z

def format_2section_relations(c):
    try:
        result = {
            "type": "2section",
            "content": []
        }

        for item in c:
            if "ความสัมพันธ์ที่ดี" in item:
                header = "ความสัมพันธ์ที่ดี"
            elif "ความสัมพันธ์ที่ปะทะ" in item:
                header = "ความสัมพันธ์ที่ปะทะ"
            else:
                continue

            # Extract animal names in Thai
            import re
            animals = re.findall(r"([ก-๙]+) \([A-Za-z]+\)", item)
            icons = [animal_thai_to_eng(animal) for animal in animals if animal_thai_to_eng(animal)]

            # Extract meaningful description (after colon or animal names)
            content_text = item.split(":")[-1]
            if "เป็นคู่มิตร" in content_text:
                content = "เป็นคู่มิตรที่ช่วยเสริมความสงบสุขและความสมดุลในชีวิต"
            else:
                content = content_text.strip()

            result["content"].append({
                "header": header,
                "icon": icons,
                "content": content
            })

        return result
    except:
        result = {
            "type": "2section",
            "content": [
                {
                    "header": "ความสัมพันธ์ที่ดี",
                    "icon": [],
                    "content": "-"
                },
                {
                    "header": "ความสัมพันธ์ที่ปะทะ",
                    "icon": [],
                    "content": "-"
                }]
        }


def convert_iso_dates_to_underscored(data):
    def transform_date_string(s):
        match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(T[\d:.]+)?$", s)
        if match:
            year, month, day, time_part = match.groups()
            return f"{year}_{month}_{day}{time_part or ''}"
        return s

    if isinstance(data, dict):
        return {k: convert_iso_dates_to_underscored(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_iso_dates_to_underscored(item) for item in data]
    elif isinstance(data, str):
        return transform_date_string(data)
    else:
        return data
    
def animal_thai_to_eng(thai_name):
    mapping = {
        "หนู": "rat",
        "วัว": "ox",
        "เสือ": "tiger",
        "กระต่าย": "rabbit",
        "มังกร": "dragon",
        "งู": "snake",
        "ม้า": "horse",
        "แพะ": "goat",
        "แกะ": "goat",         # same meaning
        "ลิง": "monkey",
        "ไก่": "rooster",
        "สุนัข": "dog",
        "หมา": "dog",          # informal synonym
        "หมู": "pig"
    }
    return mapping.get(thai_name.strip(), None)

def generate_prompt(order_id,user_id):
    global CD, GIF
    def get_basic_user_info(line_id: str):
    
        client = MongoClient(MONGO_URL)
        DATABASE_NAME = "users"
        db = client[DATABASE_NAME]
        collection = db["user_profiles"]

        basic_info = collection.find_one({"line_id": line_id})
        basic_info = dict(basic_info)
        for key in ['_id','created_at','updated_at','user_question_left','period_available','history_log','period_predictions','period_predictions_gpt','detail',]:
            basic_info.pop(key, None)
        return basic_info 

    def get_general_info():
        current_date = Api2CurrentYearMonthEnergy()
        current_anual_energy = Api3FiveYearEnergyForecast()
        monthly_energy_of_current_year = Api4NextWeekDailyEnergy()

        z = {
            'current_date' : current_date,
            'current_anual_energy' : current_anual_energy,
            'monthly_energy_of_current_year' : monthly_energy_of_current_year
        }

        return z 

    client = MongoClient(MONGO_URL)
    DATABASE_NAME = "your_database"
    db = client[DATABASE_NAME]
    collection = db["ai_prompts5"]
    
    results = list(collection.find({'id':order_id}))
    client.close()

    # debug_print('results',results)

    r = {}
    if results:
        r['basic_info'] = get_basic_user_info(user_id)

        # print('-+'*100)
        # print("r['basic_info']['birth_date']",r['basic_info']['birth_date'])
        birth_date = r['basic_info']['birth_date']
        birth_dt = datetime.strptime(birth_date, "%Y-%m-%d")
        now = datetime.now()
        age = relativedelta(now, birth_dt)
        r['basic_info']['age'] = f"Age: {age.years} years, {age.months} months"

        # print("r['basic_info']",r['basic_info'])

        r['prompt'] = results[0]['prompt']
        r['question'] = results[0]['question']

        if results[0]['requirements'] == "API1":
            api2 = None
        else:
            # print('CD,datetime.now().date()',CD,datetime.now().date())
            if CD != datetime.now().date():
                GIF = get_general_info()
                CD = datetime.now().date()
            
            r['general_info'] = GIF

    msg = f"question : {r['question']}"
    msg += f"\n\nuser_information : {r['basic_info']}"
    if 'general_info' in r.keys():
        msg += f"\ngeneral_information : {r['general_info']}"
    msg += f"\n\n{r['prompt']}"

    return msg,r

def convert_to_structure(text):
    result = []
    lines = text.strip().split('\n')
    
    current_block = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("-"):
            # เป็นหัวข้อใหม่
            if current_block:
                result.append(current_block)
            current_block = {
                "title": stripped,
                "type": "text",
                "content": ""
            }
        else:
            # เป็น bullet point
            if current_block:
                current_block["content"]= stripped.lstrip("- ").strip()
    
    # อย่าลืมเพิ่ม block สุดท้าย
    if current_block:
        result.append(current_block)
    
    return result

# def convert_to_structure(text):
#     result = []
#     lines = text.strip().split('\n')
    
#     current_block = None

#     for line in lines:
#         stripped = line.strip()
#         if not stripped:
#             continue
#         if not stripped.startswith("-"):
#             # เป็นหัวข้อใหม่
#             if current_block:
#                 result.append(current_block)
#             current_block = {
#                 "title": stripped,
#                 "type": "bullet",
#                 "content": []
#             }
#         else:
#             # เป็น bullet point
#             if current_block:
#                 current_block["content"].append(stripped.lstrip("- ").strip())
    
#     # อย่าลืมเพิ่ม block สุดท้าย
#     if current_block:
#         result.append(current_block)
    
#     return result

def convert_to_structure2(text: str) -> dict:
    keys = [
        "intro",
        "power_of_day",
        "emotional_impact",
        "highlight_of_day",
        "things_to_do",
        "things_to_avoid",
        "power_to_use_today",
        "energy_to_recharge",
        "lucky_color",
        "lucky_crystal",
        "summary",
    ]

    lines = text.strip().split("\n")
    day_name = lines[0].strip()

    sections = {}
    current_key = None
    buffer = []

    for line in lines[1:]:
        line_strip = line.strip()
        if line_strip in keys:
            if current_key:
                sections[current_key] = "\n".join(buffer).strip()
            current_key = line_strip
            buffer = []
        else:
            buffer.append(line)
    if current_key:
        sections[current_key] = "\n".join(buffer).strip()

    # ลบบรรทัดที่ขึ้นต้นด้วย - และรวมเป็นข้อความเดียว
    def format_text(text):
        cleaned_lines = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("-"):
                line = line[1:].strip()
            cleaned_lines.append(line)
        return " ".join(cleaned_lines).strip()

    # จัดเป็น bullet list
    def format_bullet(text):
        items = [line[2:].strip() for line in text.split("\n") if line.strip().startswith("-")]
        return {"type": "bullet", "content": items}

    # === Return เฉพาะ key ที่ต้องการ ===
    return {
        "day_name": day_name,
        "intro": format_text(sections.get("intro", "")),
        "power_of_day": format_bullet(sections.get("power_of_day", "")),
        "emotional_impact": format_bullet(sections.get("emotional_impact", "")),
        "highlight_of_day": format_bullet(sections.get("highlight_of_day", "")),
        "things_to_do": format_bullet(sections.get("things_to_do", "")),
        "things_to_avoid": format_bullet(sections.get("things_to_avoid", "")),
        "power_to_use_today": format_bullet(sections.get("power_to_use_today", "")),
        "energy_to_recharge": format_bullet(sections.get("energy_to_recharge", "")),
        "lucky_color": format_bullet(sections.get("lucky_color", "")),
        "lucky_crystal": format_bullet(sections.get("lucky_crystal", "")),
        "summary": format_text(sections.get("summary", "")),
    }


def _run_gpt_update_worker(line_id: str) -> None:
    """Run the GPT calendar rebuild in a background thread and track status."""
    _update_gpt_status(
        line_id,
        status="running",
        started_at=_now_iso(),
        message="GPT calendar generation is processing.",
    )
    try:
        summary = UpdatePeriodGPTAll(line_id)
        _update_gpt_status(
            line_id,
            status="completed",
            completed_at=_now_iso(),
            message="GPT calendar generation finished.",
            result=summary,
        )
    except Exception as exc:  # noqa: BLE001
        import traceback

        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        print(f"UpdatePeriodGPTAll worker crashed for {line_id}: {exc} ({type(exc).__name__})\n{tb}")
        _update_gpt_status(
            line_id,
            status="error",
            completed_at=_now_iso(),
            message=str(exc),
            last_error=str(exc),
            traceback=tb,
        )
    finally:
        if line_id in BG_STD_TASK:
            BG_STD_TASK.remove(line_id)
        _update_gpt_status(line_id, queue_size=len(BG_STD_TASK))


def run_UpdatePeriodGPTAll_in_background(line_id: str):
    global BG_STD_TASK 
    if line_id in BG_STD_TASK:
        print('x'*100)
        print('BG_STD_TASK',BG_STD_TASK)
        print(f'{line_id} exist process')
        print('x'*100)
        return {
            "status": "running",
            "line_id": line_id,
            "queue_size": len(BG_STD_TASK),
            "message": "GPT calendar generation already running for this user.",
            "details": get_gpt_task_status(line_id),
        }

    queue_size = len(BG_STD_TASK) + 1
    entry = _update_gpt_status(
        line_id,
        status="queued",
        queue_size=queue_size,
        started_at=_now_iso(),
        message="GPT calendar generation started in background.",
        processed_dates=0,
        successful_count=0,
        failed_count=0,
        failed_results=[],
        pending_dates=None,
        total_dates=None,
        last_request=None,
    )

    thread = threading.Thread(target=_run_gpt_update_worker, args=(line_id,), daemon=True)
    thread.start()

    BG_STD_TASK.append(line_id)
    return {
        "status": "started",
        "line_id": line_id,
        "queue_size": len(BG_STD_TASK),
        "message": "GPT calendar generation started in background.",
        "details": copy.deepcopy(entry),
    }

def UpdatePeriodGPTAll(line_id):
    global BG_STD_TASK 

    _update_gpt_status(
        line_id,
        status="running",
        message="Preparing GPT calendar rebuild.",
        started_processing_at=_now_iso(),
    )

    def get_peroid_aval(line_id):
            DATABASE_NAME = "users"
            COLLECTION_NAME = "user_profiles"

            # Connect to MongoDB
            client = MongoClient(MONGO_URL)
            db = client[DATABASE_NAME]
            collection = db[COLLECTION_NAME]

            # Find document with date = "2025-02-07"
            query = {"line_id": line_id}
            result = collection.find_one(query)

            return result['period_available']

    def update_std_day(line_id,target_date):
        def cal_std_day(line_id,target_date):
            def find_day_name(date):
                DATABASE_NAME = "your_database"
                COLLECTION_NAME = "calendar_profiles_2568"

                # Connect to MongoDB
                client = MongoClient(MONGO_URL)
                db = client[DATABASE_NAME]
                collection = db[COLLECTION_NAME]

                # Find document with date = "2025-02-07"
                query = {"date": date}
                result = collection.find_one(query)
                return result['day_name'],result['theme']

            def get_basic_user_info(line_id: str):
            
                client = MongoClient(MONGO_URL)
                DATABASE_NAME = "users"
                db = client[DATABASE_NAME]
                collection = db["user_profiles"]

                basic_info = collection.find_one({"line_id": line_id})
                basic_info = dict(basic_info)
                for key in ['_id','created_at','updated_at','user_question_left','period_available','history_log','period_predictions','period_predictions_gpt','detail',]:
                    basic_info.pop(key, None)
                return basic_info 
            
            day_name,theme = find_day_name(target_date)
            debug_print('day_name',day_name)
        
            api1_info = get_basic_user_info(line_id)
            api2_info = Api2CurrentYearMonthEnergy(target_date)

            text_input = f'day_name: {day_name}'
            text_input += str(api1_info)
            text_input += str(api2_info)

            text_input += get_config_prompts()['calendar_prompt_header'] + '\n'
            text_input += get_config_prompts()['calendar_prompt_footer']
            # text_input += """วิเคราะห์พลังงานของคุณในวันนี้ 
            #             intro (เกริ่นนำ)
            #             power_of_day (พลังงานวันนี้ของฉันเป็นอย่างไร)
            #             emotional_impact (ผลกระทบต่ออารมณ์ของฉันจากพลังงานวันนี้)
            #             highlight_of_day (เรื่องเด่นของวันนี้ ในด้านการเงิน งาน ความสัมพันธ์ และสุขภาพ)
            #             things_to_do (วันนี้ฉันควรทำอะไรเพื่อเป็นฉันในเวอร์ชั่นที่ดีที่สุด)
            #             things_to_avoid (วันนี้ฉันไม่ควรทำอะไรเพื่อเป็นฉันในเวอร์ชั่นที่ดีที่สุด)
            #             power_to_use_today (พลังงานเด่นที่ฉันควรหยิบมาใช้ในวันนี้)
            #             energy_to_recharge (พลังงานที่ต้องเติม พร้อมแนวคิดและการลงมือทำ)
            #             lucky_color (สีที่เสริมพลัง)
            #             lucky_crystal (อัญมณีที่เสริมพลัง)
            #             summary (สรุปและคำแนะนำในการดำเนินชีวิตวันนี้)

            #             หลักเกณฑ์ในการให้คำตอบ:
            #             ✅ ให้คำแนะนำที่นำไปปฏิบัติได้จริง → ไม่ใช่แค่ “แนะนำทั่วไป” แต่ต้องประกอบด้วย การปรับที่แนวคิดและวิธีการดำเนินการ เพื่อให้เกิดการนำไปใช้จริง และ ลงมือทำ
            #             ✅ กำหนดกรอบวิเคราะห์ให้ชัดเจน → ให้คำแนะนำแบบเป็นขั้นตอน ลงรายละเอียดทั้งการปรับวิธีคิด และ วิธีลงมือทำ
            #             ✅ โฟกัสที่ "แนวคิด" และ "วิธีปฏิบัติ" → ชี้ให้เห็นว่าปกติคุณจะทำอย่างไร เปลี่ยนเป็นควรจะปรับอย่างไรเพื่อประโยชน์ที่ดีกว่า
            #             ✅ ใช้ภาษาที่นำไปใช้จริงได้ → ไม่ใช่คำตอบแบบกว้างๆ แต่ต้องมีตัวอย่างและขั้นตอนชัดเจน
            #             ✅ใช้คำแนะนำเป็นภาษาปกติ ไม่ใช้ศัพท์จากความรู้Bazi ไม่กล่าวถึงธาตุ นักษัตร 10 Profiles 5 Structures หรือ ศัพท์ทางเทคนิคBazi ไม่ต้องให้เหตุผลว่า Bazi มีองค์ประกอบอะไร แต่แสดงเฉพาะผลจากการวิเคราะห์ เป็นภาษาที่อ่านง่าย ชัดเจน กระชับ และน่าติดตาม
            #             ✅ ไม่ใช้ภาษาอังกฤษโดยไม่มีคำแปลภาษาไทย และ หลีกเลี่ยงการใช้คำศัพท์ที่ซับซ้อนหรือเทคนิคเฉพาะทาง
            #             ✅ ใช้คำว่า "คุณ" แทน "เจ้าชะตา" เพื่อความเป็นกันเองและเข้าใจง่าย
            #             ✅ เชื่อมโยงกับไลฟ์สไตล์ และให้คำแนะนำเป็นขั้นตอนที่สามารถนำไปปรับใช้ได้ทันที เพื่อให้คุณสามารถพัฒนาตัวเองให้เป็นเวอร์ชันที่ดีที่สุด
            #             ✅ มีน้ำเสียงที่เป็นมิตร จริงใจ และเป็นกันเอง เหมาะสำหรับกลุ่มเป้าหมายอายุ 30-65 ปี
            #             ✅ สรุปให้กระชับ พร้อมคำแนะนำที่สามารถนำไปใช้ได้จริง
            #             เป้าหมาย: เพื่อให้รู้และเข้าใจพลังงานที่กระทบเข้ามา และ นำไปปรับใช้กับแผนการดำเนินชีวิตได้อย่างเหมาะสมมีประสิทธิภาพและประสิทธิผลสูงสุด"""
            # text_input += """
            #                 รูปแบบการส่งคำตอบ 
            #                 day_name
            #                 - (ตัวอย่าง วันจันทร์ที่ 1 กรกฎาคม พ.ศ. 2568)
            #                 intro
            #                 - xxx
            #                 power_of_day 
            #                 - xxx
            #                 - xxx
            #                 emotional_impact
            #                 - xxx
            #                 - xxx
            #                 highlight_of_day
            #                 - xxx
            #                 - xxx
            #                 things_to_do
            #                 - xxx
            #                 - xxx
            #                 things_to_avoid
            #                 - xxx
            #                 - xxx
            #                 power_to_use_today
            #                 - xxx
            #                 - xxx
            #                 energy_to_recharge
            #                 - xxx
            #                 - xxx
            #                 lucky_color (เฉพาะชื่ออย่างเดียว)
            #                 - xxx 
            #                 - xxx
            #                 lucky_crystal (เฉพาะชื่ออย่างเดียว)
            #                 - xxx
            #                 - xxx
            #                 summary
            #                 - xxx

            #                 ข้อกำหนดรูปแบบ (บังคับ):
            #                 - แต่ละหัวข้อ (topic) ต้องมีเพียง 1 บรรทัดชื่อหัวข้อ ตามด้วย 1 บรรทัด bullet ที่ขึ้นต้นด้วยเครื่องหมาย “-” เพียงอันเดียว
            #                 - ห้ามใช้ตัวหนา/ตัวเอียง/โค้ดบล็อก/ตาราง/ลิงก์ ในคำตอบ
            #                 - ห้ามมีคำนำ/บทสรุป/ข้อความใดๆ นอกเหนือจากคู่ “หัวข้อ + bullet”
            #                 - ทุกหัวข้อจำเป็นต้องมี bullet และทุก bullet ต้องอยู่ใต้หัวข้อเดียวเท่านั้น (สัมพันธ์แบบ 1:1)
            #                 - เนื้อหาใน bullet ต้องยาวไม่น้อยกว่า 400 ตัวอักษร (นับทุกอักขระ รวมเว้นวรรคและอีโมจิ), อธิบายเชิงลึก, ใส่อีโมจิได้ตามความเหมาะสม
            #                 - จำนวนและลำดับหัวข้อให้ยึดตามโจทย์/คำสั่งของผู้ใช้โดยเคร่งครัด (ห้ามเพิ่มหรือลดหัวข้อเอง)
            #                 - ห้ามมีบรรทัดว่างคั่นระหว่างหัวข้อ
            #                 - ห้ามมีรายการย่อยหลายข้อภายในบรรทัด bullet เดียว
            #                 - หากข้อมูลไม่พอให้ครบ 400 ตัวอักษร ให้ขยายความประเด็นที่เกี่ยวข้องโดยยังคงตรงประเด็น
            #                 - ข้อกำหนดทั้งหมดนี้ใช้กับ “คำตอบ” ที่ส่งให้ผู้ใช้ ไม่ใช่ข้อความตั้งค่า/คำอธิบายของระบบ   
            #                 """
            
            debug_print('text_input',text_input)
            status_code, payload = call_gpt(text_input)

            if status_code != 200:
                raise RuntimeError(f"GPT call failed ({status_code}): {payload}")

            res = convert_to_structure2(payload)

            res['day_name'] = day_name
            res['theme'] = theme.strip('"').strip("'")
            debug_print('------======')
            debug_print(res)
            return res, status_code
            
        res, status_code = cal_std_day(line_id,target_date)
        debug_print(res)

        client = MongoClient(MONGO_URL)
        db = client["users"]
        collection = db["user_profiles"]

        collection.update_one(
            {"line_id": line_id},
            {"$set": {f"period_predictions_gpt.{target_date}": res}},
            upsert=True
        )
        return {"status_code": status_code, "result": res}

    pv = get_peroid_aval(line_id)
    debug_print(pv)

    start = datetime.strptime(pv['start_date'], '%Y-%m-%d')
    end = datetime.strptime(pv['end_date'], '%Y-%m-%d')
    all_dates = [(start + timedelta(days=i)).date().isoformat() for i in range((end - start).days + 1)]

    # 👇 Load existing prediction keys from MongoDB
    client = MongoClient(MONGO_URL)
    db = client["users"]
    collection = db["user_profiles"]
    user_data = collection.find_one({"line_id": line_id}, {"period_predictions_gpt": 1})

    existing_dates = []
    if user_data and "period_predictions_gpt" in user_data:
        existing_dates = list(user_data["period_predictions_gpt"].keys())

    # 👇 Filter out dates that already exist
    pending_dates_list = [d for d in all_dates if d not in existing_dates]
    skipped_existing = len(all_dates) - len(pending_dates_list)


    debug_print(len(pending_dates_list))
    debug_print('-')


    total_dates = len(pending_dates_list)
    summary_data = {
        "line_id": line_id,
        "total_dates": total_dates,
        "processed_dates": 0,
        "successful_count": 0,
        "failed_count": 0,
        "failed_results": [],
        "skipped_existing": skipped_existing,
        "last_request": None,
    }
    _update_gpt_status(
        line_id,
        total_dates=total_dates,
        pending_dates=total_dates,
        processed_dates=0,
        successful_count=0,
        failed_count=0,
        failed_results=[],
        skipped_existing=skipped_existing,
        last_request=None,
    )

    for target_date in pending_dates_list:
        request_result = None
        try:
            request_result = update_std_day(line_id, target_date)
            summary_data["successful_count"] += 1
            summary_data["last_request"] = {
                "date": target_date,
                "status": "success",
                "status_code": request_result.get("status_code") if isinstance(request_result, dict) else None,
                "message": "GPT response stored.",
            }
        except Exception as exc:  # noqa: BLE001
            import traceback

            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            print(f"UpdatePeriodGPTAll: failed to update {target_date} for {line_id}: {exc} ({type(exc).__name__})\n{tb}")
            summary_data["failed_count"] += 1
            failure_entry = {"date": target_date, "error": str(exc)}
            summary_data["failed_results"].append(failure_entry)
            summary_data["failed_results"] = summary_data["failed_results"][-10:]
            summary_data["last_request"] = {
                "date": target_date,
                "status": "error",
                "message": str(exc),
            }
        finally:
            summary_data["processed_dates"] += 1
            _update_gpt_status(
                line_id,
                processed_dates=summary_data["processed_dates"],
                successful_count=summary_data["successful_count"],
                failed_count=summary_data["failed_count"],
                pending_dates=max(total_dates - summary_data["processed_dates"], 0),
                failed_results=summary_data["failed_results"],
                last_request=summary_data["last_request"],
            )

    summary = {
        "line_id": line_id,
        "total_dates": total_dates,
        "processed_dates": summary_data["processed_dates"],
        "successful_count": summary_data["successful_count"],
        "failed_count": summary_data["failed_count"],
        "failed_results": summary_data["failed_results"],
        "skipped_existing": skipped_existing,
    }
    _update_gpt_status(
        line_id,
        processed_dates=summary["processed_dates"],
        successful_count=summary["successful_count"],
        failed_count=summary["failed_count"],
        pending_dates=max(total_dates - summary["processed_dates"], 0),
        failed_results=summary["failed_results"],
        skipped_existing=skipped_existing,
        last_request=summary_data["last_request"],
    )
    return summary


def get_config_prompts():
    client = MongoClient(MONGO_URL)
    db = client["your_database"]
    collection = db["config_prompts"]

    # ดึงข้อมูลทั้งหมด
    results = list(collection.find({}))

    # แปลง _id ให้เป็น string
    for r in results:
        r["_id"] = str(r["_id"])

    client.close()
    return results[0]
