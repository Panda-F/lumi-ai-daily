export type RemotionWord = {
  text: string;
  start_frame: number;
  end_frame: number;
  absolute_start_frame: number;
  absolute_end_frame: number;
};

export type SubtitleCue = {
  start_frame: number;
  end_frame: number;
  text: string;
};

export type OpeningItem = {
  index: number;
  label: string;
  icon?: string | null;
};

export type ScreenCard = {
  heading: string;
  body: string;
  icon_hint: string;
};

export type MediaKind = "image" | "gif" | "video";

export type MediaAsset = {
  src: string;
  kind: MediaKind;
  source_domain: string;
  priority: number;
  selector?: string | null;
  image_url?: string | null;
};

export type ShotRegion = {
  kind: string;
  start_frame: number;
  end_frame: number;
  absolute_start_frame: number;
  absolute_end_frame: number;
};

export type LayoutVariant = "intro" | "full_media" | "fact_card" | "quote_card";
export type TemplateVariant =
  | "intro_light"
  | "media_then_quote"
  | "quote_dominant"
  | "fact_dominant_fallback"
  | "research_quote_fallback"
  | "outro_light";

export type TransitionMarker = {
  frame: number;
  scene_id: string;
  scene_kind: "item";
  scene_start_frame: number;
};

export type RemotionSceneBase = {
  id: string;
  kind: "intro" | "item" | "outro";
  start_frame: number;
  end_frame: number;
  duration_frames: number;
  still_frame: number;
  script: string;
  oral_script: string;
  subtitle_script: string;
  audio_src?: string | null;
  audio_offset_frames?: number;
  audio_duration_frames?: number;
  words: RemotionWord[];
  subtitle_cues: SubtitleCue[];
  layout_variant: LayoutVariant;
  template_variant: TemplateVariant;
  shot_regions: ShotRegion[];
  media_assets: MediaAsset[];
  primary_media_src?: string | null;
  primary_media_kind?: MediaKind | null;
};

export type IntroScene = RemotionSceneBase & {
  kind: "intro";
  layout_variant: "intro";
  template_variant: "intro_light";
  date_label: string;
  item_count_label: string;
  issue_label: string;
  title: string;
  subtitle: string;
  trend_words: string[];
  headlines: string[];
  opening: string;
  agenda: string;
  transition: string;
  agenda_lines: string[];
  opening_items?: OpeningItem[];
  lead_title: string;
  lead_media_src?: string | null;
  lumi_intro_src?: string | null;
  lumi_intro_kind?: MediaKind | null;
};

export type ItemCardType = "screenshot" | "text" | "quote";

export type ItemScene = RemotionSceneBase & {
  kind: "item";
  item_kind: string;
  index: number;
  current_index: number;
  total_items: number;
  title: string;
  display_title: string;
  spoken_title: string;
  spoken_aliases: Array<{ from: string; to: string }>;
  short_title: string;
  display_icon?: string | null;
  content: string;
  interpretation: string;
  quote: string;
  hook: string;
  takeaway: string;
  fact_points: string[];
  screen_cards: ScreenCard[];
  source_note: string;
  outro: string;
  source_domain: string;
  source_url: string;
  status?: string | null;
  card_type: ItemCardType;
  image_src?: string | null;
  image_srcs?: string[];
  media_usage?: string;
  media_reject_reason?: string | null;
  style_variant?: string | null;
};

export type OutroScene = RemotionSceneBase & {
  kind: "outro";
  template_variant: "outro_light";
  line_one: string;
  line_two: string;
  quote_id?: string;
  quote_text: string;
  quote_translation: string;
  quote_author: string;
};

export type RemotionScene = IntroScene | ItemScene | OutroScene;

export type ReportItemSummary = {
  index: number;
  title: string;
  item_label?: string;
  source_url: string;
};

export type RemotionManifest = {
  renderer: "remotion";
  version: number;
  meta: {
    date: string;
    title: string;
    issue_label: string;
    item_count: number;
    item_labels?: string[];
    total_frames: number;
    width: number;
    height: number;
    design_width: number;
    design_height: number;
    aspect_ratio: string;
    fps: number;
    layout: string;
    intro_style: string;
    subtitle_mode: string;
    tts_reference_id?: string;
    html_baseline?: string;
    intro_duration_sec?: number;
    style_review_status?: string;
    bgm_src?: string | null;
    bgm_volume?: number;
    bgm_provider?: string;
    bgm_label?: string;
    bgm_start_frame?: number;
    bgm_end_frame?: number | null;
    outro_bgm_enabled?: boolean;
    transition_sfx_src?: string | null;
    transition_sfx_volume?: number;
    transition_sfx_provider?: string;
    transition_sfx_label?: string;
    transition_markers?: TransitionMarker[];
    lumi_avatar_src?: string | null;
    lumi_intro_kind?: MediaKind | null;
    editorial_title_card?: boolean;
    card_preview_media?: boolean;
    primary_hook?: string;
    issue_quote_text?: string;
    issue_quote_original?: string;
    issue_quote_author?: string;
    quote_id?: string;
  };
  report: {
    trend_words: string[];
    items: ReportItemSummary[];
  };
  scenes: RemotionScene[];
};
