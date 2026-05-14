"""
Jholey Doctor — Expanded Eval Set (75 cases)
Run: python3 eval_cases.py
Requires: webapp running on localhost:8501 with no ACCESS_PIN
"""
import asyncio
import httpx
import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

BASE_URL = "http://localhost:8501"

@dataclass
class EvalCase:
    id: int
    category: str
    description: str
    symptoms: str
    age: Optional[str]
    sex: Optional[str]
    expected_level: str
    must_not_contain: list
    must_contain: list
    language: str = "en"

KEYWORD_ANCHORING_CASES = [
    EvalCase(1,"keyword_anchoring","Burning on sphincter → anorectal, not burn injury","burning sensation on my sphincter","30","male","YELLOW",["burn injury","skin burn","thermal","fire burn"],["fissure","hemorrhoid","piles","anorectal","anal","perianal"]),
    EvalCase(2,"keyword_anchoring","Burning when urinating → UTI, not burn","burning when I urinate since 2 days","25","female","YELLOW",["burn injury","skin burn","fire"],["uti","urinary","urethritis","cystitis","dysuria"]),
    EvalCase(3,"keyword_anchoring","Shooting pain in chest → cardiac, not gunshot","shooting pain in chest since this morning","45","male","YELLOW",["gunshot","wound","ballistic","penetrating trauma"],["cardiac","angina","musculoskeletal","pleurisy","costochondritis"]),
    EvalCase(4,"keyword_anchoring","Stabbing pain in abdomen → abdominal pain, not stab wound","stabbing pain in my abdomen after eating","35","female","YELLOW",["stab wound","penetrating injury","knife"],["gastric","peptic","abdominal","appendicitis","gastritis"]),
    EvalCase(5,"keyword_anchoring","Tearing pain in back → musculoskeletal, not laceration","tearing pain in my lower back when I bend","40","male","YELLOW",["laceration","tear wound","cut"],["muscle","disc","lumbar","back pain","sprain"]),
    EvalCase(6,"keyword_anchoring","Pins and needles in leg → neurological, not foreign body","pins and needles in my left leg for a week","50","female","YELLOW",["foreign body","pin inserted","needle injury"],["nerve","neuropathy","peripheral","radiculopathy","circulation"]),
    EvalCase(7,"keyword_anchoring","Pressure in chest → cardiac, not physical compression","pressure in my chest and left arm heaviness","55","male","RED",["compression injury","weight on chest","physical pressure"],["cardiac","angina","myocardial","heart attack","ischemia"]),
    EvalCase(8,"keyword_anchoring","Burning stomach → gastric, not burn injury","burning in my stomach after spicy food","28","male","YELLOW",["burn injury","skin burn","thermal burn"],["gastric","acidity","reflux","gerd","peptic ulcer"]),
    EvalCase(9,"keyword_anchoring","Burning throat → pharyngitis/reflux, not burn","burning sensation in my throat since 3 days","22","female","YELLOW",["burn injury","chemical burn","thermal burn of throat"],["pharyngitis","reflux","gerd","tonsillitis","acid"]),
    EvalCase(10,"keyword_anchoring","Cutting pain in knee → musculoskeletal, not laceration","cutting pain in my right knee when I walk","60","male","YELLOW",["laceration","cut wound","skin cut"],["arthritis","meniscus","knee pain","osteoarthritis","ligament"]),
]

ANORECTAL_CASES = [
    EvalCase(11,"anorectal","Rectal bleeding → hemorrhoids/fissure","blood in stool and pain in anal area for 1 week","35","male","YELLOW",["burn","skin"],["hemorrhoid","fissure","rectal bleeding","piles","anal"]),
    EvalCase(12,"anorectal","Itching anus → perianal","itching and discomfort around my anus","40","female","YELLOW",["burn injury"],["hemorrhoid","perianal","fungal","worm","pruritus ani"]),
    EvalCase(13,"anorectal","Burning after passing stool → fissure","burning pain after passing stool, blood on toilet paper","27","male","YELLOW",["burn injury","thermal burn"],["fissure","hemorrhoid","anal","rectal"]),
    EvalCase(14,"anorectal","Swelling near anus → abscess","painful swelling near my anus, feels warm and tender","32","male","YELLOW",["burn"],["abscess","perianal","fistula","infection"]),
]

URINARY_CASES = [
    EvalCase(15,"urinary","Classic UTI female","burning when urinating, frequent urination, lower abdomen pain","24","female","YELLOW",["burn injury"],["uti","urinary tract infection","cystitis","urethritis"]),
    EvalCase(16,"urinary","UTI in Hindi — dysuria","peshab karte waqt jalan, baar baar peshab aana","30","female","YELLOW",["burn injury","fire"],["uti","urinary","dysuria","infection"]),
    EvalCase(17,"urinary","Blood in urine","blood in urine and pain in lower back for 2 days","45","male","YELLOW",["burn"],["hematuria","kidney stone","uti","urinary","renal"]),
    EvalCase(18,"urinary","Penile discharge → STI","yellowish discharge from penis for 4 days","22","male","YELLOW",["burn injury"],["gonorrhea","sti","urethritis","chlamydia","std","discharge"]),
    EvalCase(19,"urinary","Urinary retention","unable to pass urine since 6 hours, lower abdomen swelling","65","male","RED",["burn"],["retention","obstruction","bph","prostate","catheter"]),
]

DANGER_SIGN_CASES = [
    EvalCase(20,"danger_signs","Unconscious patient","patient is unconscious, not responding to voice","50","male","RED",[],["refer","hospital","emergency","unconscious"]),
    EvalCase(21,"danger_signs","Convulsion in child","child had convulsions for 2 minutes, now drowsy","4","female","RED",[],["seizure","convulsion","refer","hospital","emergency"]),
    EvalCase(22,"danger_signs","Heavy bleeding after delivery","heavy bleeding from vagina after delivery 2 hours ago","25","female","RED",[],["postpartum","hemorrhage","refer","emergency","bleeding"]),
    EvalCase(23,"danger_signs","Breathing difficulty — blue lips","difficulty breathing, lips turning blue, cannot speak full sentences","60","male","RED",[],["cyanosis","respiratory","refer","emergency","oxygen"]),
    EvalCase(24,"danger_signs","Child not waking — meningitis signs","child not waking up, stiff neck, high fever since yesterday","3","male","RED",[],["meningitis","refer","emergency","hospital","neck stiffness"]),
    EvalCase(25,"danger_signs","Amputation — finger cut off","finger cut off in agricultural machine accident","30","male","RED",[],["amputation","refer","emergency","hospital"]),
    EvalCase(26,"danger_signs","Anaphylaxis after bee sting","bee sting 10 minutes ago, throat swelling, difficulty breathing, rash all over","20","female","RED",[],["anaphylaxis","allergic","refer","emergency","epinephrine"]),
    EvalCase(27,"danger_signs","Diabetic — not waking","diabetic patient not waking up, found unconscious at home","55","male","RED",[],["hypoglycemia","diabetic","emergency","refer","glucose"]),
]

PAEDIATRIC_CASES = [
    EvalCase(28,"paediatric","Diarrhea in child under 5 → minimum YELLOW","loose stool 4 times today","3","male","YELLOW",[],["ors","dehydration","rehydration","diarrhea","fluid"]),
    EvalCase(29,"paediatric","Fever in newborn → RED","fever in a 15 day old baby, not feeding well","0","female","RED",[],["neonatal","refer","hospital","emergency","sepsis"]),
    EvalCase(30,"paediatric","Child not feeding — danger sign","6 month old baby not feeding for 12 hours, very weak, lethargic","0","male","RED",[],["refer","emergency","hospital","dehydration"]),
    EvalCase(31,"paediatric","Mild fever in 7 year old — GREEN if no other signs","mild fever since yesterday, child is active and eating well, no rash","7","female","GREEN",["refer to hospital","emergency"],["paracetamol","monitor","fever","fluids"]),
    EvalCase(32,"paediatric","Diarrhea 3x/day any age → YELLOW","loose stool 3 times per day for 2 days","25","female","YELLOW",[],["ors","diarrhea","rehydration","fluid"]),
]

MULTILINGUAL_CASES = [
    EvalCase(33,"multilingual","Hindi — bukhar with body ache","3 din se bukhar hai, body mein dard, bhook nahi lag rahi","28","male","YELLOW",[],["fever","malaria","dengue","viral","typhoid"]),
    EvalCase(34,"multilingual","Hinglish — chest pain with sweating","chest mein dard ho raha hai aur bahut paseena aa raha hai","50","male","RED",[],["cardiac","heart","refer","emergency"]),
    EvalCase(35,"multilingual","Bengali — peshab jalan","পেশাব করতে জ্বালা করছে, ঘন ঘন পেশাব হচ্ছে","22","female","YELLOW",["burn injury"],["uti","urinary","infection","dysuria"]),
    EvalCase(36,"multilingual","Nepali — diarrhea with vomiting","पखाला र बान्ता भइरहेको छ, कमजोर महसुस भइरहेको छ","8","male","YELLOW",[],["diarrhea","dehydration","ors","gastroenteritis"]),
    EvalCase(37,"multilingual","Sadri — fever and cough","bukhar aur khansi ho raha hai, teen din se","35","female","YELLOW",[],["fever","respiratory","infection","viral"]),
]

SKIN_CASES = [
    EvalCase(38,"skin","Burning skin rash — not burn injury","burning itchy rash on both arms for 3 days, no injury","25","female","YELLOW",["burn injury","thermal burn","fire burn"],["dermatitis","eczema","allergic","rash","contact"]),
    EvalCase(39,"skin","Actual burn from hot water — correctly identify","hot water spilled on my hand 1 hour ago, blisters forming","30","female","YELLOW",["uti","anorectal","cardiac"],["burn","blister","scald","wound care"]),
    EvalCase(40,"skin","Scabies — itching at night","severe itching at night between fingers and groin, 2 weeks","15","male","YELLOW",["burn"],["scabies","mite","pruritus","skin infection"]),
    EvalCase(41,"skin","Infected wound with pus","wound on foot with pus and swelling, getting worse","45","male","YELLOW",["burn injury"],["infection","abscess","wound","antibiotics","cellulitis"]),
]

OBSTETRIC_CASES = [
    EvalCase(42,"obstetric","Pregnancy with bleeding → RED","7 months pregnant, vaginal bleeding started 1 hour ago","26","female","RED",[],["placenta","antepartum","refer","emergency","bleeding"]),
    EvalCase(43,"obstetric","Vaginal discharge → STI workup","yellowish foul smelling vaginal discharge for 5 days","23","female","YELLOW",["burn injury"],["vaginal discharge","infection","sti","bacterial vaginosis","cervicitis"]),
    EvalCase(44,"obstetric","Eclampsia signs","8 months pregnant, severe headache, blurred vision, swollen face and hands","22","female","RED",[],["pre-eclampsia","eclampsia","refer","emergency","blood pressure"]),
    EvalCase(45,"obstetric","Normal pregnancy complaint — morning sickness","nausea and vomiting in the morning, 2 months pregnant","24","female","GREEN",["emergency","refer to hospital"],["morning sickness","pregnancy","nausea","hydration","small meals"]),
]

GREEN_CASES = [
    EvalCase(46,"green","Common cold, mild, adult","mild runny nose and sneezing for 1 day, no fever, active and eating well","30","male","GREEN",["refer to hospital","emergency"],["cold","viral","rest","fluids","symptomatic"]),
    EvalCase(47,"green","Minor cut — small superficial","small superficial cut on finger while cooking, bleeding stopped","35","female","GREEN",["refer to hospital","emergency","suture"],["clean","dress","antiseptic","wound","minor"]),
    EvalCase(48,"green","Mild headache, no red flags","mild headache since this afternoon, no fever, no vomiting, no neck stiffness","25","male","GREEN",["refer to hospital","emergency","meningitis"],["paracetamol","rest","fluids","headache"]),
    EvalCase(49,"green","Insect bite, no allergy signs","mosquito bite on arm, mild itching, no swelling, no difficulty breathing","20","female","GREEN",["emergency","refer to hospital","anaphylaxis"],["insect bite","antihistamine","itching","topical"]),
    EvalCase(50,"green","Mild constipation","no bowel movement for 2 days, mild bloating, no pain","40","male","GREEN",["refer to hospital","emergency"],["constipation","fiber","fluids","laxative","diet"]),
]

EDGE_CASES = [
    EvalCase(51,"edge","Chest pain in young — musculoskeletal","sharp chest pain when I breathe deeply, started after lifting heavy bags","22","male","YELLOW",["gunshot","stab wound"],["musculoskeletal","costochondritis","pleurisy","chest pain"]),
    EvalCase(52,"edge","Abdominal pain right lower — appendicitis","pain in right lower abdomen since yesterday, worse when I walk, mild fever","19","female","RED",["stab wound"],["appendicitis","refer","surgical","hospital"]),
    EvalCase(53,"edge","Diabetic foot ulcer","non-healing wound on bottom of foot for 3 weeks, diabetic patient","58","male","YELLOW",["burn injury"],["diabetic foot","ulcer","infection","wound care","refer"]),
    EvalCase(54,"edge","Snake bite","bitten by snake on leg 30 minutes ago, swelling spreading","25","male","RED",[],["snake bite","envenomation","antivenom","refer","emergency"]),
    EvalCase(55,"edge","Malaria suspicion","fever with chills and rigor every alternate day for 5 days, sweating","30","male","YELLOW",[],["malaria","rdt","plasmodium","antimalarial","fever"]),
    EvalCase(56,"edge","Dengue suspicion","high fever, severe body pain, pain behind eyes, rash on trunk, 4 days","28","female","YELLOW",[],["dengue","platelet","fever","refer","blood test"]),
    EvalCase(57,"edge","Ear pain with discharge","right ear pain and yellowish discharge for 3 days, mild hearing loss","10","male","YELLOW",["burn"],["otitis","ear infection","discharge","antibiotic"]),
    EvalCase(58,"edge","Eye pain with vision change","right eye pain, redness, blurred vision since morning","35","female","YELLOW",["burn injury"],["eye","conjunctivitis","glaucoma","refer","vision"]),
    EvalCase(59,"edge","Psychiatric — suicidal","patient says they want to kill themselves, very depressed for weeks","22","male","RED",[],["refer","mental health","psychiatric","emergency","suicidal"]),
    EvalCase(60,"edge","Heat stroke","worker collapsed in tea garden, hot dry skin, confused, temperature very high","40","male","RED",[],["heat stroke","refer","emergency","cool","hospital"]),
    EvalCase(61,"edge","Near drowning","child pulled from pond, coughing, breathing but confused","6","male","RED",[],["near drowning","refer","emergency","hospital","respiratory"]),
    EvalCase(62,"edge","Burning feet at night → neuropathy","burning sensation in both feet especially at night, diabetic for 5 years","55","female","YELLOW",["burn injury","fire burn","thermal"],["neuropathy","diabetic","peripheral","nerve","burning feet"]),
    EvalCase(63,"edge","Burning eyes from smoke","eyes burning after smoke from fire entered room, redness and tearing","30","male","YELLOW",["anorectal","uti"],["eye","chemical","irritant","wash","conjunctivitis"]),
    EvalCase(64,"edge","Chest burning → acid reflux","burning sensation in chest after meals, especially lying down, sour taste","38","female","YELLOW",["burn injury","myocardial"],["gerd","reflux","acid","antacid","gastric"]),
    EvalCase(65,"edge","Lower back pain — renal colic","sudden severe pain in right lower back radiating to groin, came in waves","32","male","YELLOW",["burn","stab wound"],["kidney stone","renal colic","ureter","refer","pain management"]),
]

ASHA_SCENARIOS = [
    EvalCase(66,"asha_scenario","Tea garden worker — pesticide exposure","pesticide sprayed on hands and face 2 hours ago, nausea, dizziness, excessive saliva","35","male","RED",[],["organophosphate","poisoning","refer","emergency","atropine"]),
    EvalCase(67,"asha_scenario","Elderly woman — fall with hip pain","70 year old woman fell down steps, cannot walk, severe hip pain","70","female","RED",[],["fracture","hip","refer","hospital","x-ray"]),
    EvalCase(68,"asha_scenario","Newborn jaundice","3 day old baby turning yellow, not feeding well, first baby","0","male","RED",[],["jaundice","neonatal","refer","bilirubin","hospital"]),
    EvalCase(69,"asha_scenario","TB suspect","cough for more than 3 weeks, blood in sputum, weight loss, night sweats","40","male","YELLOW",[],["tuberculosis","tb","sputum","refer","test"]),
    EvalCase(70,"asha_scenario","Acute abdomen — typhoid perforation","typhoid patient, sudden severe abdominal pain, abdomen rigid, high fever","20","male","RED",[],["perforation","refer","emergency","surgical","hospital"]),
    EvalCase(71,"asha_scenario","Child malnutrition","child looks very thin, hair falling out, swollen feet and belly","2","female","RED",[],["malnutrition","kwashiorkor","marasmus","refer","nutritional"]),
    EvalCase(72,"asha_scenario","COVID-like symptoms — mild","fever, loss of taste and smell, mild cough, no breathing difficulty","30","male","YELLOW",["refer to hospital immediately","emergency"],["viral","covid","isolate","monitor","fever"]),
    EvalCase(73,"asha_scenario","Hypertensive crisis","severe headache, blurred vision, nausea, known hypertensive patient","55","female","RED",[],["hypertension","blood pressure","refer","emergency","stroke"]),
    EvalCase(74,"asha_scenario","Alcohol withdrawal","heavy drinker not had alcohol for 2 days, shaking hands, seeing things, confused","45","male","RED",[],["withdrawal","delirium","refer","emergency","alcohol"]),
    EvalCase(75,"asha_scenario","Abscess requiring drainage","painful boil on back size of an egg, hot, very tender, not improving for 5 days","28","male","YELLOW",["burn injury"],["abscess","drainage","incision","infection","antibiotics"]),
]

ALL_CASES = (KEYWORD_ANCHORING_CASES + ANORECTAL_CASES + URINARY_CASES +
             DANGER_SIGN_CASES + PAEDIATRIC_CASES + MULTILINGUAL_CASES +
             SKIN_CASES + OBSTETRIC_CASES + GREEN_CASES + EDGE_CASES + ASHA_SCENARIOS)


SYNONYM_GROUPS = {
    "gastric":        ["gastric","gerd","acid reflux","gastroesophageal","peptic","acidity","dyspepsia"],
    "reflux":         ["reflux","gerd","gastroesophageal","acid","heartburn"],
    "gerd":           ["gerd","gastroesophageal","reflux","acid reflux","heartburn"],
    "knee pain":      ["knee","knee joint","knee pain","patella","patellar"],
    "arthritis":      ["arthritis","osteoarthritis","joint","degenerative"],
    "uti":            ["uti","urinary tract infection","urinary infection","cystitis","urethritis"],
    "dysuria":        ["dysuria","painful urination","burning urination","burning on urination"],
    "urinary":        ["urinary","bladder","renal","urethra","urine"],
    "cardiac":        ["cardiac","heart","myocardial","coronary","angina","ischemia","acs"],
    "angina":         ["angina","cardiac","coronary","chest pain","ischaemia","ischemia"],
    "hemorrhoid":     ["hemorrhoid","haemorrhoid","piles","anorectal","rectal"],
    "piles":          ["piles","hemorrhoid","haemorrhoid","anorectal"],
    "fissure":        ["fissure","anal tear","anorectal","anal"],
    "anorectal":      ["anorectal","anal","rectal","perianal","sphincter"],
    "infection":      ["infection","infected","septic","bacterial","purulent"],
    "abscess":        ["abscess","collection","pus","fluctuant","incision"],
    "cellulitis":     ["cellulitis","skin infection","soft tissue infection","bacterial"],
    "respiratory":    ["respiratory","pulmonary","lung","bronchial","airway"],
    "tuberculosis":   ["tuberculosis","tb","mycobacterium","acid fast"],
    "neuropathy":     ["neuropathy","peripheral neuropathy","nerve damage","diabetic nerve"],
    "nerve":          ["nerve","neurological","neuropathy","radiculopathy","peripheral"],
    "dengue":         ["dengue","dengue fever","arboviral","aedes"],
    "malaria":        ["malaria","plasmodium","falciparum","antimalarial","rdt"],
    "refer":          ["refer","referral","hospital","emergency","transfer"],
    "emergency":      ["emergency","urgent","refer","hospital","immediate"],
    "antepartum":     ["antepartum","antenatal","placenta","abruption","previa"],
    "pre-eclampsia":  ["pre-eclampsia","preeclampsia","eclampsia","hypertension in pregnancy"],
    "eclampsia":      ["eclampsia","pre-eclampsia","hypertensive","seizure in pregnancy"],
    "dehydration":    ["dehydration","dehydrated","fluid loss","electrolyte"],
    "neonatal":       ["neonatal","newborn","neonate","infant","nicu","sncu"],
    "muscle":         ["muscle","muscular","musculoskeletal","myalgia","strain"],
    "disc":           ["disc","disk","lumbar","spinal","vertebral","herniated"],
    "fracture":       ["fracture","broken bone","crack","ortho"],
    "meningitis":     ["meningitis","meningeal","csf","neck stiffness","kernig"],
    "appendicitis":   ["appendicitis","appendix","mcburney","surgical abdomen","peritonitis"],
    "snake bite":     ["snake","envenomation","venom","antivenom"],
    "heat stroke":    ["heat stroke","hyperthermia","heat exhaustion","heat illness"],
    "withdrawal":     ["withdrawal","delirium tremens","dt","alcohol withdrawal"],
    "malnutrition":   ["malnutrition","kwashiorkor","marasmus","nutritional","underweight"],
    "jaundice":       ["jaundice","neonatal jaundice","hyperbilirubinemia","bilirubin","yellow"],
    "anaphylaxis":    ["anaphylaxis","anaphylactic","allergic reaction","severe allergy"],
    "scabies":        ["scabies","mite","sarcoptes","pruritus","itching"],
    "costochondritis":["costochondritis","musculoskeletal chest","chest wall","rib"],
    "renal colic":    ["renal colic","kidney stone","urolithiasis","nephrolithiasis","calculus"],
    "back pain":      ["back pain","backache","lumbar pain","lumbago","spinal"],
    "circulation":    ["circulation","vascular","blood flow","peripheral vascular","ischemia"],
    "tonsillitis":    ["tonsillitis","pharyngitis","throat infection","sore throat","strep"],
    "pleurisy":       ["pleurisy","pleuritis","pleural","chest wall","musculoskeletal"],
    "heart attack":   ["heart attack","myocardial infarction","mi","acs","stemi","nstemi"],
    "acidity":        ["acidity","acid","reflux","gerd","gastric","dyspepsia"],
    "meniscus":       ["meniscus","knee","cartilage","ligament","joint"],
    "ligament":       ["ligament","tendon","knee","sprain","musculoskeletal"],
    "pruritus ani":   ["pruritus ani","anal itch","perianal itch","anorectal"],
    "fistula":        ["fistula","fissure","abscess","perianal","anorectal"],
    "worm":           ["worm","parasite","helminth","pinworm","threadworm"],
    "fungal":         ["fungal","candida","tinea","dermatophyte","yeast"],
    "cystitis":       ["cystitis","uti","urinary tract infection","bladder infection"],
    "urethritis":     ["urethritis","uti","urinary","std","sti","discharge"],
    "organophosphate":["organophosphate","pesticide","cholinergic","poisoning","insecticide"],
    "kwashiorkor":    ["kwashiorkor","marasmus","malnutrition","protein energy","nutritional"],
    "marasmus":       ["marasmus","kwashiorkor","malnutrition","wasting","nutritional"],
    "near drowning":  ["near drowning","drowning","submersion","aspiration","water"],
    "suicidal":       ["suicidal","suicide","self harm","mental health","psychiatric"],
    "hypoglycemia":   ["hypoglycemia","low blood sugar","glucose","diabetic emergency"],
    "postpartum":     ["postpartum","post partum","pph","uterine atony","obstetric hemorrhage"],
    "hemorrhage":     ["hemorrhage","bleeding","haemorrhage","blood loss"],
    "retention":      ["retention","urinary retention","unable to urinate","obstruction"],
    "bph":            ["bph","prostate","benign prostatic","urinary obstruction"],
    "catheter":       ["catheter","catheterization","urinary drainage","foley"],
    "antivenom":      ["antivenom","anti-venom","snake bite treatment","envenomation"],
    "atropine":       ["atropine","anticholinergic","organophosphate treatment","pralidoxime"],
    "epinephrine":    ["epinephrine","adrenaline","epipen","anaphylaxis treatment"],
    "glucose":        ["glucose","dextrose","sugar","hypoglycemia treatment"],
    "bilirubin":      ["bilirubin","jaundice","phototherapy","neonatal jaundice"],
    "platelet":       ["platelet","thrombocytopenia","dengue","blood count"],
    "sputum":         ["sputum","sputum test","afb","acid fast","tb test"],
    "perforation":    ["perforation","peritonitis","surgical abdomen","acute abdomen"],
    "blood pressure": ["blood pressure","hypertension","bp","hypertensive"],
    "stroke":         ["stroke","cerebrovascular","tia","neurological emergency"],
    "delirium":       ["delirium","confusion","altered consciousness","encephalopathy"],
    "drainage":       ["drainage","incision","i&d","surgical drainage","debridement"],
    "incision":       ["incision","drainage","i&d","surgical","debridement"],
    "morning sickness":["morning sickness","nausea in pregnancy","hyperemesis","pregnancy nausea"],
    "isolate":        ["isolate","isolation","quarantine","home isolation"],
    "cool":           ["cool","cooling","ice","cold water","temperature reduction"],
    "wash":           ["wash","irrigate","flush","rinse","eye wash"],
    "topical":        ["topical","cream","ointment","lotion","antihistamine cream"],
    "laxative":       ["laxative","stool softener","fiber","constipation treatment"],
    "antihistamine":  ["antihistamine","cetirizine","loratadine","anti-allergy"],
    "antacid":        ["antacid","omeprazole","pantoprazole","ppi","h2 blocker","ranitidine"],
    "antimalarial":   ["antimalarial","chloroquine","artemisinin","act","rdt"],
    "antibiotic":     ["antibiotic","antibiotics","amoxicillin","azithromycin","ciprofloxacin"],
    "wound care":     ["wound care","dressing","clean wound","antiseptic","wound management"],
    "pain management":["pain management","analgesic","painkiller","nsaid","antispasmodic"],
    "blood test":     ["blood test","lab test","cbc","complete blood count","investigation"],
    "x-ray":          ["x-ray","xray","radiograph","imaging","bone scan"],
    "nutritional":    ["nutritional","nutrition","therapeutic food","f75","f100","rutf"],
    "ors":            ["ors","oral rehydration","rehydration salts","electrolyte solution"],
    "rehydration":    ["rehydration","ors","oral rehydration","fluid replacement"],
    "fluid":          ["fluid","fluids","hydration","oral rehydration","iv fluid"],
    "paracetamol":    ["paracetamol","acetaminophen","antipyretic","fever reducer"],
    "monitor":        ["monitor","monitoring","observe","watch","follow up"],
    "symptomatic":    ["symptomatic","supportive","rest","fluids","home care"],
    "minor":          ["minor","superficial","small","mild","self-limiting"],
    "clean":          ["clean","cleanse","antiseptic","wound cleaning","saline"],
    "dress":          ["dress","dressing","bandage","cover","wound care"],
    "antiseptic":     ["antiseptic","betadine","savlon","iodine","wound cleaning"],
    "rest":           ["rest","bed rest","activity restriction","home rest"],
    "fluids":         ["fluids","fluid","hydration","water","oral intake"],
    "cold":           ["cold","common cold","rhinitis","upper respiratory","viral urti"],
    "viral":          ["viral","virus","viral infection","urti","flu"],
    "fever":          ["fever","pyrexia","temperature","febrile","hyperthermia"],
    "headache":       ["headache","cephalgia","head pain","migraine"],
    "constipation":   ["constipation","bowel","stool","fiber","laxative"],
    "fiber":          ["fiber","fibre","dietary fiber","roughage","constipation"],
    "diet":           ["diet","dietary","nutrition","food","eating"],
    "insect bite":    ["insect bite","mosquito bite","bug bite","arthropod"],
    "contact":        ["contact","contact dermatitis","allergic contact","irritant"],
    "dermatitis":     ["dermatitis","eczema","skin inflammation","contact","allergic"],
    "eczema":         ["eczema","dermatitis","atopic","skin rash","allergic skin"],
    "rash":           ["rash","skin rash","eruption","exanthem","urticaria"],
    "blister":        ["blister","vesicle","bulla","burn blister","fluid filled"],
    "scald":          ["scald","hot water burn","thermal burn","burn injury"],
    "burn":           ["burn","scald","thermal","hot water","fire burn"],
    "eye":            ["eye","ocular","ophthalmic","vision","conjunctiva"],
    "conjunctivitis": ["conjunctivitis","pink eye","eye infection","ocular"],
    "glaucoma":       ["glaucoma","intraocular pressure","eye pressure","optic"],
    "vision":         ["vision","visual","sight","eye","optic"],
    "otitis":         ["otitis","ear infection","otitis media","ear pain"],
    "ear infection":  ["ear infection","otitis","otitis media","aom"],
    "discharge":      ["discharge","secretion","pus","fluid","exudate"],
    "antibiotic":     ["antibiotic","antibiotics","antimicrobial","amoxicillin"],
    "vaginal discharge":["vaginal discharge","discharge","vaginitis","cervicitis"],
    "bacterial vaginosis":["bacterial vaginosis","bv","vaginitis","vaginal infection"],
    "cervicitis":     ["cervicitis","cervical infection","sti","std"],
    "sti":            ["sti","std","sexually transmitted","gonorrhea","chlamydia"],
    "gonorrhea":      ["gonorrhea","gonorrhoea","neisseria","sti","std"],
    "chlamydia":      ["chlamydia","sti","std","urethritis","cervicitis"],
    "std":            ["std","sti","sexually transmitted","gonorrhea","chlamydia"],
    "hematuria":      ["hematuria","haematuria","blood in urine","red urine"],
    "kidney stone":   ["kidney stone","renal calculus","urolithiasis","nephrolithiasis"],
    "ureter":         ["ureter","ureteral","renal colic","kidney stone","calculus"],
    "hip":            ["hip","hip joint","femur","acetabulum","hip fracture"],
    "organophosphate":["organophosphate","pesticide","op poisoning","cholinergic"],
    "poisoning":      ["poisoning","toxicity","toxic","overdose","intoxication"],
    "choking":        ["choking","airway obstruction","foreign body airway","heimlich"],
    "cyanosis":       ["cyanosis","blue lips","hypoxia","oxygen saturation","spo2"],
    "oxygen":         ["oxygen","o2","spo2","saturation","hypoxia"],
    "sepsis":         ["sepsis","septicemia","blood infection","systemic infection"],
    "unconscious":    ["unconscious","unresponsive","loss of consciousness","coma"],
    "seizure":        ["seizure","convulsion","fits","epilepsy","tonic clonic"],
    "convulsion":     ["convulsion","seizure","fits","epilepsy","tonic clonic"],
    "neck stiffness": ["neck stiffness","nuchal rigidity","meningismus","stiff neck"],
    "amputation":     ["amputation","amputated","digit loss","finger loss","limb loss"],
    "hospital":       ["hospital","refer","emergency","transfer","admit"],
    "tb":             ["tb","tuberculosis","mycobacterium","afb","acid fast bacilli"],
    "covid":          ["covid","coronavirus","sars-cov","covid-19","viral"],
    "hypertension":   ["hypertension","high blood pressure","bp","hypertensive"],
    "alcohol":        ["alcohol","ethanol","drinking","alcoholic","intoxication"],
    "psychiatric":    ["psychiatric","mental health","psychology","psychiatry"],
    "mental health":  ["mental health","psychiatric","psychology","depression","anxiety"],
    "heat exhaustion":["heat exhaustion","heat stroke","hyperthermia","heat illness"],
    "submersion":     ["submersion","drowning","near drowning","water aspiration"],
    "aspiration":     ["aspiration","inhaled","foreign body","drowning","choking"],
    "diabetic":       ["diabetic","diabetes","blood sugar","glucose","insulin"],
    "diabetic foot":  ["diabetic foot","foot ulcer","neuropathic ulcer","diabetic wound"],
    "ulcer":          ["ulcer","wound","sore","non-healing","chronic wound"],
    "envenomation":   ["envenomation","venom","snake bite","toxin","antivenom"],
    "venom":          ["venom","envenomation","snake","toxin","antivenom"],
    "burning feet":   ["burning feet","peripheral neuropathy","neuropathy","diabetic nerve"],
    "peripheral":     ["peripheral","peripheral neuropathy","nerve","extremity"],
    "irritant":       ["irritant","chemical","smoke","fumes","eye irritation"],
    "chemical":       ["chemical","irritant","toxic","corrosive","caustic"],
    "acid":           ["acid","acidity","reflux","gerd","gastric acid"],
    "antacid":        ["antacid","ppi","h2 blocker","omeprazole","ranitidine"],
    "pain management":["pain management","analgesic","nsaid","antispasmodic","buscopan"],
}

def term_matches(term: str, text: str) -> bool:
    term_lower = term.lower()
    if term_lower in text:
        return True
    synonyms = SYNONYM_GROUPS.get(term_lower, [])
    return any(s in text for s in synonyms)


async def run_case(client: httpx.AsyncClient, case: EvalCase) -> dict:
    try:
        data = {"symptoms": case.symptoms, "language": case.language, "response_lang": case.language}
        if case.age: data["age"] = case.age
        if case.sex: data["sex"] = case.sex
        resp = await client.post(f"{BASE_URL}/triage", data=data, timeout=120)
        result = resp.json()
        triage_level = result.get("triage_level", "UNKNOWN")
        full_text = " ".join([
            " ".join(result.get("differential", [])),
            result.get("summary", ""),
            " ".join(result.get("reasoning", [])),
            " ".join(result.get("actions", [])),
        ]).lower()
        level_pass = triage_level == case.expected_level
        matched_contain = [t for t in case.must_contain if term_matches(t, full_text)]
        failed_contain  = [t for t in case.must_contain if not term_matches(t, full_text)]
        matched_not     = [t for t in case.must_not_contain if t.lower() in full_text]
        must_contain_pass = len(failed_contain) == 0
        must_not_pass     = len(matched_not) == 0
        passed = level_pass and must_contain_pass and must_not_pass
        return {"id": case.id, "category": case.category, "description": case.description,
                "passed": passed, "level_pass": level_pass, "content_pass": must_contain_pass,
                "safety_pass": must_not_pass, "expected": case.expected_level, "got": triage_level,
                "matched_contain": matched_contain, "failed_contain": failed_contain,
                "failed_not": matched_not, "summary": result.get("summary",""),
                "differential": result.get("differential",[]), "auto_upgraded": result.get("auto_upgraded",False)}
    except Exception as e:
        return {"id": case.id, "category": case.category, "description": case.description,
                "passed": False, "error": str(e), "expected": case.expected_level, "got": "ERROR"}


async def run_eval():
    print(f"\n{'='*65}")
    print(f"  JHOLEY DOCTOR — EVAL SUITE ({len(ALL_CASES)} cases)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*65}\n")
    results = []
    async with httpx.AsyncClient() as client:
        for i, case in enumerate(ALL_CASES):
            print(f"[{i+1:02d}/{len(ALL_CASES)}] {case.category:<20} {case.description[:42]:<42}", end=" ", flush=True)
            r = await run_case(client, case)
            results.append(r)
            if r.get("error"):
                print(f"❌ ERROR: {r['error']}")
            elif r["passed"]:
                print(f"✅ PASS  ({r['got']})")
            else:
                issues = []
                if not r["level_pass"]:       issues.append(f"level: expected {r['expected']} got {r['got']}")
                if not r.get("content_pass"): issues.append(f"missing: {r.get('failed_contain',[])}")
                if not r.get("safety_pass"):  issues.append(f"hallucinated: {r.get('failed_not',[])}")
                print(f"❌ FAIL  ({' | '.join(issues)})")

    total        = len(results)
    passed       = sum(1 for r in results if r["passed"])
    level_pass   = sum(1 for r in results if r.get("level_pass", False))
    content_pass = sum(1 for r in results if r.get("content_pass", True))
    safety_pass  = sum(1 for r in results if r.get("safety_pass", True))
    errors       = sum(1 for r in results if r.get("error"))
    red_results  = [r for r in results if r["expected"] == "RED"]
    red_passed   = sum(1 for r in red_results if r["passed"])
    red_missed   = sum(1 for r in red_results if not r.get("level_pass") and r["got"] != "RED")
    categories   = {}
    for r in results:
        c = r["category"]
        if c not in categories: categories[c] = {"total":0,"passed":0}
        categories[c]["total"] += 1
        if r["passed"]: categories[c]["passed"] += 1

    print(f"\n{'='*65}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*65}")
    print(f"  Overall:        {passed}/{total} ({passed/total*100:.1f}%)")
    print(f"  Level accuracy: {level_pass}/{total} ({level_pass/total*100:.1f}%)")
    print(f"  Content check:  {content_pass}/{total} ({content_pass/total*100:.1f}%)")
    print(f"  Safety check:   {safety_pass}/{total} ({safety_pass/total*100:.1f}%)")
    print(f"  Errors:         {errors}")
    print(f"\n  RED Case Performance (most critical):")
    print(f"  RED passed:     {red_passed}/{len(red_results)} ({red_passed/max(len(red_results),1)*100:.1f}%)")
    print(f"  Missed RED:     {red_missed} (false negatives — DANGEROUS)")
    print(f"\n  By Category:")
    for cat, stats in sorted(categories.items()):
        pct = stats["passed"] / stats["total"] * 100
        bar = "█" * int(pct // 10) + "░" * (10 - int(pct // 10))
        print(f"  {cat:<22} {bar} {stats['passed']:02d}/{stats['total']:02d} ({pct:.0f}%)")

    output = {"timestamp": datetime.now().isoformat(), "total": total, "passed": passed,
              "accuracy": round(passed/total*100,1), "red_missed": red_missed,
              "category_breakdown": categories, "cases": results}
    with open("eval_results_v2.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Full results saved to eval_results_v2.json")
    print(f"{'='*65}\n")

if __name__ == "__main__":
    asyncio.run(run_eval())
