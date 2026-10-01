# Comparison with Kim et al. 2019 — report text

Reproduce the numbers with
`uv run python src/engine/gates/notebooks/toehold_and/kim2019_benchmark.py`.

---

## English

Kim et al. (2019) built the closest published architecture to the A0 gate and measured it,
which makes their constructs a validation set for our scoring rather than merely a
reference. Their switch places an inhibitory hairpin, lacking both start codon and ribosome
binding site, immediately 5' of the AUG/RBS-containing primary hairpin, and uses a second
trigger RNA to open it; the Shine–Dalgarno-to-start spacing (6 nt), the 21-nt linker and the
pattern-prevention list are the same as ours. The essential difference is the exposed
toehold length `a` of the primary hairpin: they tested `a` = 10, 7 and 4 nt and reported
qualitatively different behaviour — at `a` = 10 the primary trigger activates output on its
own, so the circuit acts as a one-input switch with an auxiliary tuning input, while at
`a` = 4 both triggers are required and the circuit behaves as a two-input AND gate. Our
design takes `a` to 0, the extreme of that same series. Notably, they applied no objective
function and no thresholds: sequences were designed at the domain level with NUPACK, then
built and measured, and the reported apparent Hill coefficients (2.8 for one hairpin, 7.0
for two) are fitted to dose–response data rather than predicted. There is therefore no
published computational scoring scheme for this architecture to inherit.

Passing their tested constructs through our own four-tube evaluation produced an
unambiguous and instructive result. Their primary trigger carries a full 30-nt contiguous
reverse complement of its own switch — the entire trigger, and more than the 18-nt arm our
design rules specify — so the primary hairpin can be displaced without the secondary
trigger's help. Accordingly our model returns `dG_open(10)` = 1.61 kcal/mol and
`A_M(10)` = 0.789 identically for all three spacings **and** for the single-hairpin control
that has no inhibitory hairpin at all: a working AND gate, a leaky one-input switch and a
plain toehold switch are indistinguishable to us. Our hard gate τ4a (`A_M(10)` < 0.2)
therefore rejects a construct that demonstrably functions at the bench. The discrimination
Kim observed is explicitly attributed by them to reduced *binding probability* and enforced
*sequential binding* — kinetic quantities that an equilibrium end-state model does not
represent. We conclude that our observables are computed correctly but that τ4a is not a
valid criterion for this architecture, and that the AND behaviour of a zero-spacer design
cannot be verified thermodynamically. Reassuringly, with state 10 excluded their working
`a` = 4 construct scores `separation` = 11.83 kcal/mol, squarely within the 8.5–17.5
kcal/mol range of our own candidates: by every measure our model can resolve, our designs
are not inferior to a validated one.

---

## עברית

‎Kim ועמיתיו (2019) בנו את הארכיטקטורה המתועדת הדומה ביותר לשער A0 ומדדו אותה, ולכן
המבנים שלהם מהווים מערך אימות לפונקציית הניקוד שלנו ולא רק אסמכתא. במתג שלהם ממוקמת
סיכת שיער מעכבת, נטולת קודון התחלה ואתר קישור ריבוזום, מיד במעלה הזרם (‏5'‎) לסיכת השיער
הראשית הנושאת את ה-AUG וה-RBS, ו-RNA מדליק שני פותח אותה; המרווח בין רצף שיין-דלגרנו
לקודון ההתחלה (6 נוקלאוטידים), המקשר באורך 21 נוקלאוטידים ורשימת הרצפים האסורים זהים
לשלנו. ההבדל המהותי הוא אורך אזור ה-toehold החשוף `a` של הסיכה הראשית: הם בדקו
‎`a` = 10, 7 ו-4 נוקלאוטידים ודיווחו על התנהגות שונה באיכותה — ב-`a` = 10 המדליק הראשי
מפעיל את הביטוי בכוחות עצמו, כך שהמעגל מתנהג כמתג חד-כניסה עם כניסת כיוונון נוספת, ואילו
ב-`a` = 4 נדרשים שני המדליקים והמעגל מתנהג כשער AND דו-כניסות. התכנון שלנו מביא את `a`
לאפס, כלומר לקצה אותו רצף בדיקות. ראוי לציין שהם לא השתמשו בפונקציית מטרה ולא בסף
כלשהו: הרצפים תוכננו ברמת הדומיינים באמצעות NUPACK, ולאחר מכן נבנו ונמדדו, ומקדמי
ההיל המדווחים (2.8 לסיכה אחת, 7.0 לשתיים) הותאמו לנתוני מנה-תגובה ולא נחזו מראש. אין
אפוא שיטת ניקוד חישובית מתועדת לארכיטקטורה זו שניתן לאמץ.

הרצת המבנים שנבדקו אצלם דרך הערכת ארבעת המבחנות שלנו הניבה תוצאה חד-משמעית ומאירת
עיניים. המדליק הראשי שלהם נושא משלים הופכי רציף באורך 30 נוקלאוטידים שלמים אל המתג
שלו עצמו — כלומר המדליק כולו, ויותר מהזרוע באורך 18 נוקלאוטידים שכללי התכנון שלנו
מגדירים — ולכן ניתן לעקור את הסיכה הראשית ללא סיוע מהמדליק המשני. בהתאם, המודל שלנו
מחזיר ‎`dG_open(10)` = 1.61 קק"ל/מול ו-`A_M(10)` = 0.789 באופן זהה עבור שלושת המרווחים
**וגם** עבור בקרת הסיכה הבודדת שאין בה סיכה מעכבת כלל: שער AND עובד, מתג חד-כניסה
דולף ומתג toehold פשוט אינם נבדלים זה מזה בעינינו. לפיכך הסף הקשיח שלנו τ4a
(‏`A_M(10)` < 0.2‎) פוסל מבנה שמתפקד באופן מוכח בספסל הניסויים. את ההבחנה שקים צפה בה
הם עצמם מייחסים במפורש להפחתת *הסתברות הקישור* ולכפיית *קישור סדרתי* — כמויות קינטיות
שמודל שיווי-משקל של מצב סופי אינו מייצג. מכאן אנו מסיקים שהנצפים שלנו מחושבים נכון, אך
ש-τ4a אינו קריטריון תקף לארכיטקטורה זו, וכי לא ניתן לאמת תרמודינמית את התנהגות ה-AND
של תכנון חסר מרווח. מנחם לגלות שבהחרגת מצב 10, המבנה העובד שלהם ב-`a` = 4 מקבל
‎`separation` = 11.83 קק"ל/מול, בדיוק בתוך הטווח 8.5–17.5 קק"ל/מול של המועמדים שלנו: בכל
מדד שהמודל שלנו מסוגל להבחין בו, התכנונים שלנו אינם נחותים מתכנון מאומת.

---

## Open for later: calibrating our weights against Kim's measurements

Not now, recorded so it is not lost. Kim report fitted apparent Hill coefficients for a
series of switches that differ in one controlled parameter, which is the closest thing to a
calibration set this architecture has. Two cautions before using it.

It is a **rank-order check, not a fit**: there are far too few constructs to fit a weight
to, and §4.6 of the objective-function document rules that out explicitly. The defensible
use is to ask whether our score reproduces their ordering, and to report where it does not.

And it cannot calibrate the coupling. Their two triggers are unrelated sequences binding
separate hairpins, whereas ours share the overlap `x` — so their set constrains the primary
hairpin's behaviour but says nothing about the shared-overlap mechanism that distinguishes
A0. That gap closes only with our own first panel, which argues for keeping that panel
diverse on the axes of greatest uncertainty rather than filling it with top-ranked designs.
