# Diet & Cheat Carousel Workflow

Codex skill. تحوّل نص السلايدات النهائي إلى صور كاروسيل Instagram بهوية Diet & Cheat (OLD شيلد أو NEW hands-and-heart)، كل السلايدات تتولّد **بالتوازي**، وتتحفظ في فولدر في `~/Downloads`. الـAI **مايراجعش** الصور — المستخدم يراجع.

## التسطيب

```bash
curl -fsSL https://raw.githubusercontent.com/abdullah-elbedwehy/diet-cheat-carousel-workflow/main/install.sh | bash
```

أو يدوي:

```bash
git clone https://github.com/abdullah-elbedwehy/diet-cheat-carousel-workflow.git ~/.codex/skills/diet-cheat-carousel-workflow
```

المتطلبات: macOS، `codex` CLI مسجّل دخول (`codex login`)، `python3`، `git`.

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

```
slides/      ← النهائي 1080x1440
source/      ← الخام من الموديل
history/     ← نسخ قديمة بعد أي regenerate
logs/        ← لوج كل worker + البرومبت بالظبط
brief.md     ← النص اللي بعتّه حرفيًا
prompts.md   ← البرومبتات المستخدمة
job.json     ← ملف التشغيل
manifest.json
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
| `scripts/generate.py job.json` | يشغّل worker لكل سلايد بالتوازي، يصدّر 1080x1440، يكتب manifest |
| `scripts/generate.py job.json --only 2,4 --output-dir <dir>` | إعادة توليد سلايدات محددة |
| `scripts/generate.py job.json --dry-run` | يكتب البرومبتات من غير توليد |
| `scripts/learn.py` | إدارة الدروس |
| `scripts/update.sh` | تحديث السكيل |

## الملفات

- `SKILL.md` — تعليمات الـagent.
- `references/` — الهوية، التكوينات، عقد البرومبت، الوركفلو، التعلم.
- `assets/` — اللوجوهات والمراجع.
- `docs/` — design spec.

## License

MIT
