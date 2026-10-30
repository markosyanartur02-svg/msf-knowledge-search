# Held-out check (heldout.json)

31 answerable and 9 no-answer questions, app settings (reranker, best-match order, 50% threshold, spelling correction), calibration not refitted.

| Measure | Result |
|---|---|
| Relevant document in top 5 (Recall@5) | 97% |
| Answered with a relevant document shown | 100% |
| Answered, but only wrong documents shown | 0% |
| Said 'no confident match' although answer exists | 0% |
| No-answer questions with results shown (false alarm) | 11% |
| Shown results that are labelled relevant (lower bound) | 32% |
| Search time median / slowest | 762 ms / 1485 ms |

| Kind | Recall@5 | Answered correctly |
|---|---|---|
| abbreviation (2) | 100% | 100% |
| cross-lingual (3) | 100% | 100% |
| dutch (2) | 100% | 100% |
| natural (23) | 96% | 100% |
| typo (1) | 100% | 100% |

## Every question

- `h01` [natural] how do you diagnose tuberculosis in young children? -> **OK** (rank 5) | 66% Tuberculose › Avant-propos; 72% In 2021 and 2022, tuberculosis (TB) research delivered promi; 67% Int J Tuberc Lung Dis 24(12):1265–1271
- `h02` [natural] oral rehydration for cholera patients -> **OK** (rank 1) | 70% MSF International Activity Report 2019; 70% MSF Activity Report 2010; 69% Massive humanitarian response needed to avoid health catastr
- `h03` [typo] malria simptoms (searched as "malaria symptoms") -> **OK** (rank 1) | 58% MSF Activity Report 2010; 49% Ready-to-Use Therapeutic Food for Catch-Up Growth in Childre; 52% InRakhine State,on thewestern border of Myanmar, the efficac
- `h04` [abbreviation] PPH management -> **OK** (rank 1) | 65% Essential obstetric and newborn care › 8.2 Early postpartum ; 56% Decentralised Hepatitis C Management: A Simplified, Integrat; 55% نداء مشترك للجنة الدولية للصليب الأحمر ومنظمة الصحة العالمية
- `h05` [abbreviation] RUTF for malnourished children -> **OK** (rank 1) | 86% Ready-to-Use Therapeutic Food for Catch-Up Growth in Childre; 84% MSF International Activity Report 2019; 81% Reducing Wasting in Young Children With Preventive Supplemen
- `h06` [natural] responding to a measles epidemic -> **OK** (rank 2) | 74% Management of a measles epidemic › Authors/Contributors; 74% MSF International Activity Report 2019; 70% Management of a measles epidemic › Preface
- `h07` [dutch] symptomen van malaria -> **OK** (rank 1) | 51% MSF Activity Report 2010; 38% Me´decine et Sante´ Tropicales 2018 ; 28 : 18-21 2es Journée; 38% Malaria and nutritional status among children with severe ac
- `h08` [natural] protecting health workers during an Ebola outbreak -> **OK** (rank 1) | 86% Duty of care and health worker protections in the age of Ebo; 81% Improving Ebola virus disease outbreak control through targe; 79% MSF International Activity Report 2019
- `h09` [natural] hepatitis C treatment results in Cambodia -> **OK** (rank 7) | 85% Cambodia 2019 Activity Report; 82% High sustained viral response rate in patients with hepatiti; 81% MSF International Activity Report 2019
- `h10` [natural] routine viral load monitoring for people on ART -> **OK** (rank 1) | 89% Journey towards universal viral load monitoring in Maputo, M; 87% Scale-up of Routine Viral Load Testing in Resource-Poor Sett; 84% Superior Virologic and Treatment Outcomes When Viral Load is
- `h11` [natural] diabetes care in humanitarian settings -> **OK** (rank 1) | 75% Management of diabetes and associated costs in a complex hum; 67% MSF experiences of providing multidisciplinary primary level; 67% André Heller Pérache, MSc Crystal van Leeuwen, RN and Master
- `h12` [natural] medical care for survivors of sexual violence -> **OK** (rank 1) | 82% MSF International Activity Report 2019; 80% MSF Activity Report 2010; 76% Les Cahiers Du Crash Msf And Protection: Pe,Nding Or Closen?
- `h13` [natural] psychosocial support for young children in refugee camps -> **OK** (rank 1) | 75% Evaluation Of The Psychosocial Impacts Of Baby Friendly Spac; 65% Cameroon; 65% MSF Activity Report 2000-2001
- `h14` [natural] scabies outbreak in Rohingya camps -> **OK** (rank 1) | 81% Unprecedented increase of scabies cases in Cox’s Bazar refug; 63% Inadequate water and sanitation pose health threats in Syria; 57% Laurence Binet Msf And The Rohingya The Msf Speaking Out Cas
- `h15` [natural] dialysis for kidney patients during a crisis -> **OK** (rank 1) | 65% André Heller Pérache, MSc Crystal van Leeuwen, RN and Master; 54% MSF Activity Report 2010; 55% استمرار الاحتياجات الطبية وسط النزاع في السودان
- `h16` [natural] cancer care in Papua New Guinea -> **OK** (rank 1) | 87% Papua New Guinea: Strengthening cancer care in Morobe; 68% MSF International Activity Report 2019; 59% MSF International Activity Report 2014
- `h17` [natural] rescuing migrants at sea in the Mediterranean -> **OK** (rank 1) | 87% Health conditions of migrants, refugees and asylum seekers o; 80% It was in the 1980s when the first bodies of migrants and re; 79% MSF International Activity Report 2019
- `h18` [natural] cholera in Haiti -> **OK** (rank 1) | 87% Research Protocol - Factors Related to Fetal Death in Pregna; 83% Vaccines and urgent response needed as cholera wave rises in; 82% MSF International Activity Report 2014
- `h19` [natural] healthcare after the earthquake in northwest Syria -> **OK** (rank 1) | 90% Northwest Syria: Providing healthcare amongst the rubble in ; 89% شمال غرب سويا: توفير الرعاية الصحية بين الأنقاض في جنديرس; 81% Year in Review 2023
- `h20` [natural] impact of aid cuts on MSF clinics -> **OK** (rank 1) | 87% Aid cuts force mass clinic closures across Sudan; 73% Resumen del año 2022; 67% The Medecins Sans Frontieres Charter Medecins Sans Frontiere
- `h21` [natural] clean water for displaced families in Lebanon -> **OK** (rank 1) | 90% Bringing clean water and sanitation to forcibly displaced fa; 86% توفير المياه النظيفة وخدمات الصرف الصحي للأسر النازحة قسرًا ; 59% Laurence Binet Msf And The Rohingya The Msf Speaking Out Cas
- `h22` [natural] why do Rohingya mothers give birth at home? -> **OK** (rank 1) | 90% Why mothers give birth at home: exploration of Rohingya refu; 61% صحة الأم والطفل وضع طارئ منسيّ في أزمة جمهورية إفريقيا الوسط; 57% Laurence Binet Msf And The Rohingya The Msf Speaking Out Cas
- `h23` [natural] who is protected under international humanitarian law? -> **OK** (rank 2) | 84% Les Cahiers Du Crash Msf And Protection: Pe,Nding Or Closen?; 87% Protected Persons; 67% Laurence Binet War Crimes And Politics Of Terror In Chechnya
- `h24` [natural] what are the humanitarian principles? -> **OK** (rank 1) | 90% Humanitarian Principles; 70% Laurence Binet War Crimes And Politics Of Terror In Chechnya; 56% Les Cahiers Du Crash Msf And Protection: Pe,Nding Or Closen?
- `h25` [natural] role of the International Criminal Court -> **OK** (rank 1) | 86% International Criminal Court (ICC); 80% Genocide; 48% Guía clínica y terapéutica › Abreviaturas y siglas
- `h26` [natural] MSF and the Rwandan genocide -> **OK** (rank 1) | 89% The Msf Speaking Out Case Studies Laurence Binet Genocide Of; 88% The Msf Speaking Out Case Studies Laurence Binet Genocide Of; 57% Resumen del año 2022
- `h27` [natural] MSF total expenditure in 2024 -> **OK** (rank 1) | 88% MSF International Financial Report 2024; 85% MSF International Financial Report 2021; 63% Médicaments essentiels › Auteurs/Contributeurs
- `h28` [cross-lingual] vaccination contre le choléra -> **OK** (rank 1) | 66% Use of Vibrio cholerae Vaccine in an Outbreak in Guinea; 65% Feasibility of a preventive mass vaccination campaign with t; 62% The scenario approach for countries considering the addition
- `h29` [cross-lingual] ارتفاع حالات سوء التغذية في أفغانستان -> **OK** (rank 1) | 88% أفغانستان: ارتفاع مقلق في حالات سوء التغذية الحاد بين الأطفا; 84% Alarming rise in severe malnutrition admissions in southern ; 71% Year in Review 2022
- `h30` [cross-lingual] violencia sexual en Haití -> **OK** (rank 2) | 89% Haiti 2018 Activity Report; 85% Report: Sexual and gender-based violence in Port-au-Prince; 85% MSF International Activity Report 2019
- `h31` [dutch] behandeling van cholera -> **OK** (rank 1) | 66% MSF International Activity Report 2014; 63% MSF International Activity Report 2019; 54% Research Protocol - Factors Related to Fetal Death in Pregna
- `x01` [no-answer] vasectomy procedure -> **no-answer: correctly silent** (rank >10) | 36% بيلاروسيا; 35% Comparison of Operative Logbook Experience of Australian Gen; 33% Tuberculosis › Foreword
- `x02` [no-answer] laser hair removal side effects -> **no-answer: correctly silent** (rank >10) | 47% تقديم العلاج الطبي والنفسي في محطة المترو في خاركيف أوكرانيا; 44% غزة: وسط انهيار وقف إطلاق النار تغدو المياه سلاحًا آخر للحرب; 41% Tuberculose › Avant-propos
- `x03` [no-answer] tennis elbow treatment -> **no-answer: correctly silent** (rank >10) | 39% تقديم العلاج الطبي والنفسي في محطة المترو في خاركيف أوكرانيا; 34% بيلاروسيا; 27% Tuberculosis › Foreword
- `x04` [no-answer] surgery for varicose veins -> **no-answer: correctly silent** (rank >10) | 44% بيلاروسيا; 38% Tuberculosis › Foreword; 36% تقديم العلاج الطبي والنفسي في محطة المترو في خاركيف أوكرانيا
- `x05` [no-answer] best cream for eczema in adults -> **no-answer: correctly silent** (rank >10) | 42% Medicamentos esenciales › Medicamentos de uso externo y anti; 42% Médicaments essentiels › Médicaments à usage externe et anti; 41% volume 4 no 6 pp 428–432 june 1999
- `x06` [no-answer] ADHD medication for children -> **no-answer: correctly silent** (rank >10) | 46% Int J Tuberc Lung Dis 24(12):1265–1271; 39% Medicamentos esenciales › Medicamentos de uso externo y anti; 41% In 2021 and 2022, tuberculosis (TB) research delivered promi
- `x07` [no-answer] traitement de l'eczéma -> **no-answer: correctly silent** (rank >10) | 35% Me´decine et Sante´ Tropicales 2018 ; 28 : 18-21 2es Journée; 30% Prise en charge d'une épidémie de rougeole › Avant-propos; 30% Mise En Œuvre D'Algorithmes De Décision De Traitement De La 
- `x08` [no-answer] behandeling van ADHD bij kinderen -> **no-answer: correctly silent** (rank >10) | 45% Me´decine et Sante´ Tropicales 2018 ; 28 : 18-21 2es Journée; 39% Int J Tuberc Lung Dis 24(12):1265–1271; 38% Mise En Œuvre D'Algorithmes De Décision De Traitement De La 
- `x09` [no-answer] علاج الدوالي -> **no-answer: FALSE ALARM** (rank >10) | 50% Me´decine et Sante´ Tropicales 2018 ; 28 : 18-21 2es Journée; 41% Implementation of fixed‑dose combination therapy for seconda; 41% بيلاروسيا
