# Diet & Cheat Carousel Workflow

Codex skill. تحوّل نص السلايدات النهائي إلى صور كاروسيل Instagram بهوية Diet & Cheat (OLD شيلد أو NEW hands-and-heart)، كل السلايدات تتولّد **بالتوازي**، وتتحفظ في فولدر في `~/Downloads`. الـAI **ما بيحكمش بصريًا**؛ فحوص المقاس/البكسلات/الشيلد/علامات الاقتباس ميكانيكية فقط، والمستخدم يراجع الشكل.

## التسطيب

```bash
curl -fsSL https://raw.githubusercontent.com/abdullah-elbedwehy/diet-cheat-carousel-workflow/main/install.sh | bash
```

أو يدوي:

```bash
git clone https://github.com/abdullah-elbedwehy/diet-cheat-carousel-workflow.git ~/.codex/skills/diet-cheat-carousel-workflow
```

المتطلبات: macOS، `codex` CLI مسجّل دخول (`codex login`)، `python3`، `git`. المثبّت ينشئ `.venv` ويثبت Pillow تلقائيًا.

## الاستخدام

افتح Codex في أي فولدر واكتب الهوية + السلايدات بنصها النهائي:

```
OLD.
Slide 1: كل ده بلاش ده؟
Slide 2: مقلية
الفرق هنا في الزيت والتغطية
Slide 3: ...
```

الناتج: `~/Downloads/DC-OLD-<topic>-<date>/`

التشغيل مرحلتين إجباريًا: الأول preview من غير أي توليد، وبعد موافقة صريحة فقط يبدأ التوليد:

```bash
python3 scripts/generate.py job.json --dry-run
python3 scripts/generate.py job.json --yes   # بعد go صريحة فقط
```

غياب `--yes` يوقف عند approval gate ويفتح صفر workers. الـagent لا يمرر
`--yes` من نفسه، ونفس البوابة تنطبق على `--only` regeneration.

```
slides/      ← النهائي بالمقاس الحرفي في job.size.deliver
source/      ← الخام من الموديل
history/     ← نسخ قديمة بعد أي regenerate
logs/        ← لوج كل worker + البرومبت بالظبط
brief.md     ← النص اللي بعتّه حرفيًا
prompts.md   ← البرومبتات المستخدمة
job.json     ← ملف التشغيل
manifest.json
mechanical-validation.json
run-verification.json  ← إثبات إن الـrunner والـdispatch guard نجحوا
REVIEW.md    ← جدول المراجعة
```

### إعادة توليد سلايد

```
regenerate slide 3 — الكلمة الإنجليزية اتعكست
```

السبب يتسجل كدرس ويتطبّق فورًا. النسخة القديمة تروح `history/`.

### التحديث

```
pull latest update
```

يعمل `git pull` للسكيل. الدروس المحلية مش بتتلمس.

## سستم التعلم

- `learnings/shared/lessons.md` — دروس مشتركة، بتيجي مع التحديث.
- `learnings/local/lessons.md` — دروس جهازك بس (gitignored).
- كل رن يقرأ الدروس النشطة ويحطها في البرومبت. كل فيدباك منك يتحوّل لدرس جديد.

```bash
python3 scripts/learn.py list            # الدروس النشطة
python3 scripts/learn.py runs            # آخر الرنات
python3 scripts/learn.py promote         # (للمشرف) نقل المحلي للمشترك
```

## السكريبتات

| Script | Purpose |
|---|---|
| `scripts/generate.py job.json --dry-run` | يكتب approval preview والبرومبتات، من غير أي worker أو توليد |
| `scripts/generate.py job.json --yes` | بعد موافقة صريحة: يشغّل كل workers بالتوازي ويصدّر ويفحص |
| `scripts/generate.py job.json --only 2,4 --output-dir <dir> --yes` | إعادة توليد سلايدات وافق عليها المستخدم |
| `scripts/verify_run.py <output-dir>` | يثبت إن الرن خرج من الـrunner وإن dispatch timing صالح |
| `scripts/validate.py job.json --output-dir <dir>` | يفحص المقاس، RGB/no-alpha، الخلفية، شيلد REF-01، وguillemets |
| `scripts/learn.py` | إدارة الدروس |
| `scripts/update.sh` | تحديث السكيل |

## التوازي المثبت

الـdefault هو worker مستقل لكل سلايد، والـeffective concurrency يساوي عدد السلايدات المحددة. ما تمررش `--concurrency` إلا لو المستخدم طلب cap صراحة.

قياس 2026-09-19 على الجهاز ده:

- 8 جلسات `codex exec`: start spread = `0.015150s`، و8/8 نجحوا.
- جولتان حقيقيتان، 8 Imagegen calls في كل جولة: start spread = `0.012522–0.014917s`.
- الـceiling المثبت: **8 على الأقل** للجلسات ولـImagegen. أعلى من 8 غير مختبر.

`manifest.json.dispatch` بيسجل start/completion لكل worker والـconcurrency الفعلي. `REVIEW.md` بيعرض العدد والـstart spread والحكم. أي full-parallel run يتعدى `2.0s` start spread، أو أي فولدر ناقص artifacts الأساسية، يفشل `run-verification.json`. اختلاف أوقات الانتهاء طبيعي؛ المقياس هو dispatch start spread، مش إن الملفات تظهر في نفس اللحظة.

## Export وvalidation

- مسار `sips` بيستخدم ملف crop منفصل وملف resize منفصل؛ مفيش resize in-place.
- بعد الـresize، الملف بيتقري تاني. أي اختلاف عن `job.size.deliver` hard failure من غير تقريب أو retry صامت.
- الخلفية OLD `#12181D`: أي بكسل داخل tolerance `12` لكل channel بيتثبت على اللون بالظبط. الاختيار empirical: زوايا السلايدات المرفوضة كانت داخل 7، بينما sample من الرسمة `#060B11` عدى الحد عند 13.
- الأربعة corners والـcenter لازم يبقوا `#12181D` بالظبط، والملف RGB من غير alpha.
- REF-01 لازم يظهر مرة واحدة جوه bottom-left region. absent/duplicate/outside = fail.
- لو الـcopy فيها `«»`، body crop بيتعمل له Vision OCR. لو character boxes موثوقة، الاتجاه والترتيب RTL بيتفحصوا؛ غير كده `REVIEW.md` يطبع النص `OCR-ONLY` عشان المراجعة تبقى بنظرة واحدة.
- failure ميكانيكي يعمل automatic whole-slide regeneration مرة واحدة فقط.

## Job schema 2

كل slide لازم يسجل `number`، `intent`، `subject`، `visual`، و`copy` منفصلين. الـregeneration يحافظ على `number` و`intent` و`copy`، ويحافظ على `subject` إلا لما `regeneration.failure_class` يساوي `object`.

قاعدة الـgold المعيارية موجودة مرة واحدة في `references/render-spec.md`؛ أمثلة النجاح والفشل موجودة في `references/compositions.md`. Whole gold object يوقف الـbuild قبل أي generation.

Evidence: [before crop](docs/evidence/first-week-fatigue-slide01-before.png), [after crop](docs/evidence/first-week-fatigue-slide01-after.png), and [mechanical evidence JSON](docs/evidence/first-week-fatigue-evidence.json).

## الملفات

- `SKILL.md` — تعليمات الـagent.
- `scripts/generate.py` — الـdispatcher الوحيد المسموح له يولّد الصور.
- `scripts/image_processing.py` — exact flatten + REF-01 template matching.
- `scripts/validate.py` — الفحوص الميكانيكية + `REVIEW.md`.
- `scripts/verify_run.py` — canonical-artifact وdispatch-timing guard.
- `references/` — الهوية، التكوينات، عقد البرومبت، الوركفلو، التعلم.
- `assets/` — اللوجوهات والمراجع.
- `docs/` — design spec.

## License

MIT
