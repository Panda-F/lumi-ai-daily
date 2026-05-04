# Source Modules

- `run_tech_daily_pipeline.py`: daily orchestration entry.
- `common/`: shared paths, report parser, URL/title helpers.
- `discovery/`: source discovery, source/reference archiving, X reader, Tavily search, and real story image collection.
- `content/`: factual report, content manifest, WeChat article/DOCX, title pack, and cover copy.
- `visuals/`: cover brief and cover resolver for the imagegen-based cover step.
- `video/`: video build, TTS, BGM analysis, video script payload, and Bilibili files.
- `video/remotion/`: Remotion app and render scripts.
- `intelligence/`: source policy plus editorial, writing, title, and cover guidance.
