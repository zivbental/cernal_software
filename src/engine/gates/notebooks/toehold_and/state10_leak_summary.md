# The state-10 leak — what we found, what it means, what is still open

Written 2026-09-16. Every number here is reproducible from this directory:
`design_panel.py` (the candidates), `kim2019_benchmark.py` (the published reference),
`strength_window.py` (the sweep that tested the fix). Simple summary in English first,
then in Hebrew.

---

## English

### Bottom line, in three sentences

1. **Trigger A binds the switch completely whether or not trigger B is there.** In the
   two tubes we fold, A occupies **35.93 of its 36 nt** on the switch in state 10 and
   **35.93** in state 11 — a difference of 0.004 nt. There is nothing left for B to
   enable, so at equilibrium the gate is an OR-ish single-input switch, not an AND.
2. **This is not a bug and not our design's fault.** Kim 2019's bench-validated AND gate
   fails our own test with the same numbers. Their AND works for *kinetic* reasons
   (binding probability, forced order of binding) that an equilibrium model cannot see.
3. **We tried to fix it in the main hairpin and it cannot be fixed there.** 40 redesigns
   across 10 trigger pairs, spanning a 10.7 kcal/mol swing in exactly the balance we
   thought controlled the leak, all returned `separation` **0.00**.

### What we measured on our own candidates

| Measurement | Result |
|---|---|
| `separation` (worst OFF state vs ON) | **0.00** on all 142 candidates |
| `A_M(10)` vs `A_M(11)` | equal to within **~1×10⁻⁵** on 142/142 |
| τ4a (`A_M(10) < 0.2`) | passes **0/142** |
| `separation` with state 10 excluded | 8.5 – 17.5 kcal/mol — healthy |

So every candidate looks good on states 00 and 01 and fails only on state 10. That one
state is the whole problem.

### The audit that settles the mechanism

Three earlier audits checked that `p_open`, `A_M` and `dG_open` are computed correctly
(agreement to 0.01 kcal/mol against independent re-derivations). This one asks a different
question — *where does each strand actually go?* — by summing pair probabilities per
strand pair:

| Tube | trigger A bound to switch | trigger B bound to switch | switch paired to itself | A paired to B |
|---|---|---|---|---|
| 00 (neither) | — | — | 44.3 | — |
| 01 (B only) | — | 49.69 / 50 nt | 25.2 | — |
| 10 (A only) | **35.93 / 36 nt** | — | **27.5** | — |
| 11 (both) | **35.93 / 36 nt** | 49.69 / 50 nt | 10.1 | 0.000 |

Read the last column first: the two triggers never pair with each other, so nothing here
is a dimer artefact. Then read the "switch paired to itself" column top to bottom. The
switch starts with **44.3 bp** of its own structure — the two hairpins. Trigger B alone
removes about 19 of them (→ 25.2); that is the secondary, inhibitory hairpin, which is
exactly its job. **Trigger A alone removes about 17 of them (→ 27.5) — the main hairpin,
the one holding the ribosome window shut.** With both present only 10.1 bp survive.

So trigger A dismantles the main hairpin **by itself**, and its occupancy on the switch is
the same to within 0.004 nt whether or not B is present. Both triggers bind fully, neither
blocks the other, and the structure B destroys lies outside the window we score. The gate's
design intent — B unlocks the site A needs — simply does not constrain the equilibrium end
state.

### The reference: Kim et al. 2019

Their architecture is the closest published relative of ours, and they measured it. Our
pipeline returns `dG_open(10)` = **1.61** and `A_M(10)` = **0.789** for *all four* of
their constructs: `a` = 10 (behaves as one-input), `a` = 7, `a` = 4 (**the working AND**),
and the single-hairpin control with no inhibitory hairpin at all. Identical, because the
ribosome window's sequence is identical in all four — they differ only in upstream
spacing. A working AND gate, a leaky one-input switch, and a plain toehold switch are
indistinguishable to our scoring. Kim attribute the real difference to reduced *binding
probability* and enforced *sequential* binding. Both are kinetic.

**Conclusion we can defend:** τ4a is not a valid criterion for this architecture, and no
equilibrium score can verify the AND behaviour of a zero-spacer design.

### The upper main stem — the idea we tested, and why it failed

The main hairpin has two helices with the start codon between them:

```
   5'  … main_pre*  ·  bulge*  ·  k1*  ] RBS loop [  mainZ · AUG · main_pre …  3'
           9 bp        3×3 loop    6 bp                6 bp        9 bp
        (lower helix)             (UPPER helix, next to the loop)
```

The **upper helix is `k1*:mainZ`, 6 bp**, and `mainZ` is the only sequence in the whole
arm we are free to choose. As the design stands, `mainZ = k1` = trigger A's first 6 nt, so
trigger A is complementary to the upper helix too. The idea — and it is the right instinct
— was to break that: make `mainZ` an unrelated 6-mer so trigger A loses 6 of its 18 base
pairs while the stem keeps all 18. Then trigger A should lose to the stem alone and win
only once trigger B frees the extra `len_x` pairs. That is a real window:

```
grip_with_x  <  stem  <  grip_alone
```

We swept **all 4096 possible spacers** per trigger pair with a no-folding energy proxy
(seconds, not hours), kept the ones inside the window, and folded a sample **spread across
the whole margin range** so the answer would be a curve and not a cherry-picked best case.

**Result: the window is empty.** 40 variants, 10 trigger pairs, margins from 0.1 to 10.7
kcal/mol inside the window — `separation` 0.00 every time, `dG_open(10) == dG_open(11)`
every time. Separation does not respond to the margin *anywhere* along a 10.7 kcal/mol
sweep, which is a much stronger negative than any single design failing.

**Why.** Trigger A never has to beat the whole 18-bp stem. It only has to peel the **lower
helix**, and there:

- `main_pre` in the switch and `main_pre` in trigger A are the **same 9 nucleotides**, so
  they bind `main_pre*` equally well; and
- trigger A additionally pairs `bulge*` with its own 3-nt `bulge`, where the switch's
  descending arm offers only the unpairable `AUG`.

R7 grants trigger A those three base pairs **by design**. `mainZ` sits on the far side of
the bulge and cannot take them back. And `main_pre` is the reporter's **first three
codons** — so it is inside the ribosome window and inside trigger A's footprint at the
same time. Peeling it opens most of the window on its own.

We also tested the obvious follow-up: give the bulge bonus to the switch instead, by making
the 3 nt facing the `AUG` complementary to the start codon (`CAU`) rather than to trigger
A. Same answer — `separation` 0.00 on every pair, alone and combined with the spacer
change. It does push `A_M(10)` down to 0.107–0.116, under τ4a's 0.2 — but `A_M(11)` falls
with it, so the gate is shut in both states and never turns ON. That is the other wall of
the window.

**What Green's architecture does differently** is keep the region covering the start codon
out of the trigger's complementary footprint, which is exactly the property our layout
lacks. *Confirming the exact stem geometry in Green 2014 is the next reading step — it is
not yet verified from here, so do not present it as established.*

### A retraction

An earlier throwaway script reported this same spacer change reaching `separation +2.97`
with `A_M(10)` 0.060 against `A_M(11)` 0.404, and that number was written into our notes
as evidence the idea worked. **It was wrong — a state-labelling error.** Its "state 10"
was the switch-alone tube. Re-measured through `four_tube_observables` on the same trigger
pair and the same spacer (x@52, `len_x` 8, `mainZ` `GCCGAC`): `separation` **−0.00**,
`A_M(10) = A_M(11) = 0.405`, and its "`A_M(10)` 0.060" is this pipeline's `A_M(00)`.
Decoupling the upper stem does lower `A_M(10)` from 0.522 to 0.405 — it just never
separates state 10 from state 11.

### Where this leaves us

**Ruled out, with measurements, so nobody spends time on them again:**

- Raising τ from 0.2 to 0.5 — arithmetically impossible while `A_M(10) == A_M(11)`.
- `engaged(10)` as a replacement leak metric — candidate x@68 has `engaged(10)` = 0.048
  (trigger A never takes its designed nucleation site) and still leaks completely.
- `len_x` — spans 0.048 to 0.858 with no relation to the leak.
- Choosing `mainZ` / decoupling the upper stem — this document.
- Moving the bulge to the switch's side — kills the ON state instead.

**Still live:**

1. **Report `separation` over {00, 01} and say so.** Honest, unblocking, and it stops
   claiming the AND is verified. This is what `design_panel.py` does today.
2. **Make the window-covering stretch independent of trigger A.** The diagnosis that
   survives the failure. It means `main_pre` stops being trigger-derived, which costs a few
   residues of N-terminal extension on the reporter, and it reopens R1 and R6.
3. **Add a kinetic term**, which is Kim's own explanation and what §4.5 of the design
   document anticipated. Canonical reference is Zhang & Winfree 2009 (toehold-mediated
   displacement rates spanning ~6 orders of magnitude over toehold length 0→6 nt) —
   **not verified from here; check it before citing it.**
4. **Build the panel and measure it.** The equilibrium model cannot distinguish a validated
   AND gate from a switch that does not gate, so for this architecture the bench is not a
   confirmation step — it is the measurement.

---

## עברית

### השורה התחתונה בשלוש נקודות

1. **מדליק A נקשר למתג במלואו, בין אם מדליק B נמצא ובין אם לא.** בשתי המבחנות שאנחנו
   מקפלים, A תפוס ב-**35.93 מתוך 36 הנוקלאוטידים** שלו על המתג במצב 10, ו-**35.93** במצב
   11 — הפרש של 0.004 נוקלאוטידים. לא נשאר שום דבר ש-B יכול לאפשר, ולכן בשיווי משקל השער
   מתנהג כמתג חד-כניסה ולא כשער AND.
2. **זה לא באג ולא כשל של התכנון שלנו.** שער ה-AND של Kim 2019, שנמדד ועבד במעבדה, נכשל
   בבדיקה שלנו באותם מספרים בדיוק. ה-AND שלהם עובד מסיבות **קינטיות** (הסתברות קישור וסדר
   קישור כפוי) שמודל שיווי משקל לא יכול לראות.
3. **ניסינו לתקן את זה בסיכת השיער הראשית, ושם אי אפשר לתקן.** 40 תכנונים חלופיים על 10
   זוגות מדליקים, שפרושים על טווח של 10.7 קק"ל/מול בדיוק באיזון שחשבנו ששולט בדליפה — כולם
   החזירו `separation` של **0.00**.

### מה מדדנו על המועמדים שלנו

| מדידה | תוצאה |
|---|---|
| `separation` (מצב ה-OFF הגרוע מול ה-ON) | **0.00** בכל 142 המועמדים |
| `A_M(10)` מול `A_M(11)` | שווים עד כדי **~1×10⁻⁵** ב-142 מתוך 142 |
| τ4a (`A_M(10) < 0.2`) | עובר **0 מתוך 142** |
| `separation` בלי מצב 10 | 8.5 – 17.5 קק"ל/מול — תקין לחלוטין |

כלומר כל מועמד נראה טוב במצבים 00 ו-01, ונכשל רק במצב 10. המצב הבודד הזה הוא כל הבעיה.

### הבדיקה שמכריעה את המנגנון

שלוש בדיקות קודמות אימתו ש-`p_open`, `A_M` ו-`dG_open` מחושבים נכון (התאמה של 0.01
קק"ל/מול מול גזירות עצמאיות). הבדיקה הזאת שואלת שאלה אחרת — **לאן כל גדיל באמת הולך?** —
על ידי סכימת הסתברויות הקישור בין כל זוג גדילים:

| מבחנה | A קשור למתג | B קשור למתג | המתג קשור לעצמו | A קשור ל-B |
|---|---|---|---|---|
| 00 (אף אחד) | — | — | 44.3 | — |
| 01 (רק B) | — | 49.69 / 50 נ׳ | 25.2 | — |
| 10 (רק A) | **35.93 / 36 נ׳** | — | **27.5** | — |
| 11 (שניהם) | **35.93 / 36 נ׳** | 49.69 / 50 נ׳ | 10.1 | 0.000 |

כדאי לקרוא קודם את העמודה האחרונה: שני המדליקים לא נקשרים זה לזה בכלל, כך ששום דבר כאן
אינו ארטיפקט של דימר. אחר כך לקרוא את העמודה "המתג קשור לעצמו" מלמעלה למטה. המתג מתחיל
עם **44.3 זוגות בסיסים** של מבנה עצמי — שתי הסיכות. מדליק B לבדו מסיר כ-19 מהם (← 25.2);
זו הסיכה המשנית המעכבת, וזה בדיוק התפקיד שלו. **מדליק A לבדו מסיר כ-17 מהם (← 27.5) —
כלומר את הסיכה הראשית, זו שמחזיקה את חלון הריבוזום סגור.** כששניהם נוכחים נשארים רק 10.1
זוגות.

כלומר מדליק A מפרק את הסיכה הראשית **בכוחות עצמו**, והתפוסה שלו על המתג זהה עד כדי 0.004
נוקלאוטידים בין מצב 10 למצב 11. שני המדליקים נקשרים במלואם, אף אחד לא חוסם את השני,
והמבנה ש-B מפרק נמצא מחוץ לחלון שאנחנו מנקדים. כוונת התכנון — ש-B יפתח את האתר ש-A זקוק
לו — פשוט לא מגבילה את מצב הקצה בשיווי משקל.

### האסמכתא: Kim ועמיתיו 2019

הארכיטקטורה שלהם היא הקרובה ביותר לשלנו מבין המתועדות, והם מדדו אותה. הפייפליין שלנו
מחזיר `dG_open(10)` = **1.61** ו-`A_M(10)` = **0.789** עבור **כל ארבעת** המבנים שלהם:
`a` = 10 (מתנהג כחד-כניסה), `a` = 7, `a` = 4 (**שער ה-AND שעובד**), ובקרת הסיכה הבודדת
שאין לה בכלל סיכה מעכבת. זהים — מפני שרצף חלון הריבוזום זהה בכל הארבעה, והם נבדלים רק
במרווח שבמעלה הזרם. שער AND עובד, מתג חד-כניסה דולף, ומתג toehold פשוט — שלושתם בלתי
ניתנים להבחנה עבור הניקוד שלנו. Kim מייחסים את ההבדל האמיתי להסתברות קישור מופחתת
ולקישור **טורי** כפוי. שניהם קינטיים.

**המסקנה שאנחנו יכולים להגן עליה:** ‏τ4a אינו קריטריון תקף לארכיטקטורה הזאת, ושום ניקוד
שיווי-משקלי לא יכול לאמת התנהגות AND בתכנון עם מרווח אפס.

### הסטם העליון של הסיכה הראשית — הרעיון שבדקנו, ולמה הוא נכשל

לסיכה הראשית יש שני סלילים, וקודון ההתחלה ביניהם:

```
   5'  … main_pre*  ·  bulge*  ·  k1*  ] לולאת RBS [  mainZ · AUG · main_pre …  3'
          9 ז״ב       לולאת 3×3   6 ז״ב              6 ז״ב       9 ז״ב
       (הסליל התחתון)                        (הסליל העליון, צמוד ללולאה)
```

**הסליל העליון הוא `k1*:mainZ`, שישה זוגות בסיסים**, ו-`mainZ` הוא הרצף היחיד בכל הזרוע
שאנחנו חופשיים לבחור. במצב התכנון הנוכחי `mainZ = k1` = ששת הנוקלאוטידים הראשונים של
מדליק A, ולכן מדליק A משלים גם את הסליל העליון. הרעיון — והאינטואיציה נכונה — היה לשבור
את זה: להפוך את `mainZ` לרצף שאינו קשור למדליק A, כך שמדליק A יאבד 6 מתוך 18 זוגות
הבסיסים שלו בעוד שהסטם שומר על כל ה-18. אז מדליק A אמור להפסיד לסטם לבדו, ולנצח רק אחרי
שמדליק B משחרר את `len_x` הזוגות הנוספים. זה חלון אמיתי:

```
grip_with_x  <  stem  <  grip_alone
```

סרקנו את **כל 4096 המרווחים האפשריים** לכל זוג מדליקים בעזרת קירוב אנרגטי בלי קיפול
(שניות, לא שעות), שמרנו את אלה שבתוך החלון, וקיפלנו מדגם **פרוש על כל טווח המרווח**, כדי
שהתשובה תהיה עקומה ולא מקרה טוב שנבחר בקפידה.

**התוצאה: החלון ריק.** 40 וריאנטים, 10 זוגות מדליקים, מרווחים מ-0.1 עד 10.7 קק"ל/מול בתוך
החלון — `separation` של 0.00 בכל פעם, ו-`dG_open(10) == dG_open(11)` בכל פעם. ה-separation
לא מגיב למרווח **באף נקודה** על פני סריקה של 10.7 קק"ל/מול, וזו שלילה חזקה בהרבה מכל
תכנון בודד שנכשל.

**למה.** מדליק A לא צריך בכלל לנצח את כל הסטם בן 18 זוגות הבסיסים. הוא צריך רק לקלף את
**הסליל התחתון**, ושם:

- `main_pre` שבמתג ו-`main_pre` שבמדליק A הם **אותם תשעה נוקלאוטידים**, ולכן הם נקשרים
  ל-`main_pre*` בדיוק באותה חוזקה; וגם
- מדליק A מזווג בנוסף את `bulge*` עם ה-`bulge` בן 3 הנוקלאוטידים שלו, במקום שבו הזרוע
  היורדת של המתג מציעה רק את ה-`AUG` שאינו יכול להזדווג.

חוק R7 מעניק למדליק A את שלושת זוגות הבסיסים האלה **מעצם התכנון**. ‏`mainZ` יושב בצד השני
של הבליטה ולא יכול לקחת אותם בחזרה. ובנוסף, `main_pre` הוא **שלושת הקודונים הראשונים**
של הגן המדווח — כלומר הוא נמצא גם בתוך חלון הריבוזום וגם בתוך טביעת הרגל של מדליק A בעת
ובעונה אחת. קילוף שלו פותח את רוב החלון בכוחות עצמו.

בדקנו גם את ההמשך המתבקש: לתת את בונוס הבליטה למתג במקום למדליק A, על ידי כך ששלושת
הנוקלאוטידים שמול ה-`AUG` יהיו משלימים לקודון ההתחלה (`CAU`) ולא למדליק A. אותה תשובה —
`separation` של 0.00 בכל זוג, גם לבד וגם בשילוב עם שינוי המרווח. זה כן מוריד את `A_M(10)`
ל-0.107–0.116, מתחת ל-0.2 של τ4a — אבל `A_M(11)` יורד יחד איתו, ולכן השער סגור בשני
המצבים ופשוט לא נדלק. זה הקיר השני של החלון.

**מה שהארכיטקטורה של Green עושה אחרת** הוא שהיא משאירה את האזור שמכסה את קודון ההתחלה
מחוץ לטביעת הרגל המשלימה של המדליק, וזו בדיוק התכונה שחסרה בפריסה שלנו. *אימות הגאומטריה
המדויקת של הסטם ב-Green 2014 הוא צעד הקריאה הבא — הוא עדיין לא אומת מכאן, ולכן אין להציג
אותו כמבוסס.*

### תיקון והסתייגות

סקריפט חד-פעמי קודם דיווח שאותו שינוי מרווח בדיוק מגיע ל-`separation` של **+2.97**, עם
`A_M(10)` של 0.060 מול `A_M(11)` של 0.404, והמספר הזה נכתב בהערות שלנו כהוכחה שהרעיון
עובד. **זה היה שגוי — שגיאת תיוג מצבים.** ה"מצב 10" שלו היה המבחנה של המתג לבדו. במדידה
חוזרת דרך `four_tube_observables`, על אותו זוג מדליקים ואותו מרווח (x@52, `len_x` 8,
`mainZ` `GCCGAC`): ‏`separation` = **−0.00**, ‏`A_M(10) = A_M(11) = 0.405`, וה"`A_M(10)`
0.060" שלו הוא בעצם ה-`A_M(00)` של הפייפליין הזה. ניתוק הסטם העליון כן מוריד את `A_M(10)`
מ-0.522 ל-0.405 — הוא פשוט לא מפריד בין מצב 10 למצב 11 לעולם.

### איפה זה משאיר אותנו

**נשלל, עם מדידות, כדי שאף אחד לא יבזבז על זה זמן שוב:**

- העלאת τ מ-0.2 ל-0.5 — בלתי אפשרית אריתמטית כל עוד `A_M(10) == A_M(11)`.
- `engaged(10)` כמדד דליפה חלופי — למועמד x@68 יש `engaged(10)` של 0.048 (מדליק A לעולם
  לא לוקח את אתר הגרעון המתוכנן שלו) והוא בכל זאת דולף לגמרי.
- `len_x` — נפרש בין 0.048 ל-0.858 בלי שום קשר לדליפה.
- בחירת `mainZ` / ניתוק הסטם העליון — המסמך הזה.
- העברת הבליטה לצד של המתג — הורגת במקום זאת את מצב ה-ON.

**עדיין פתוח:**

1. **לדווח `separation` על {00, 01} ולהגיד את זה במפורש.** כנה, משחרר את החסימה, ומפסיק
   לטעון שה-AND מאומת. זה מה ש-`design_panel.py` עושה היום.
2. **להפוך את הקטע שמכסה את החלון לבלתי תלוי במדליק A.** האבחנה ששורדת את הכישלון.
   המשמעות היא ש-`main_pre` מפסיק להיות נגזר מהמדליק, מה שעולה כמה חומצות אמינו של הארכה
   בקצה ה-N של הגן המדווח, ופותח מחדש את R1 ואת R6.
3. **להוסיף איבר קינטי**, שזה ההסבר של Kim עצמו ומה שסעיף 4.5 במסמך התכנון צפה מראש.
   האסמכתא הקנונית היא Zhang & Winfree 2009 (קצבי הדחקה מונחית-toehold שנפרשים על
   כ-6 סדרי גודל כתלות באורך toehold מ-0 ל-6 נוקלאוטידים) — **לא אומת מכאן; לבדוק לפני
   שמצטטים.**
4. **לבנות את הפאנל ולמדוד אותו.** מודל שיווי המשקל לא מצליח להבחין בין שער AND מאומת
   לבין מתג שלא מבצע שערוּר בכלל, ולכן עבור הארכיטקטורה הזאת המעבדה היא לא שלב אישור —
   היא **המדידה**.
