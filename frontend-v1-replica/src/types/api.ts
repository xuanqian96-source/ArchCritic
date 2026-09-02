// 后端接口类型：统一描述项目、提交、图纸、报告和历史记录。
export interface Project {
  id: number;
  name: string;
  building_type: string;
  owner_name: string;
  grade: string;
  site_location?: string;
  course_name?: string;
  created_at?: string | null;
}

export interface LocalUser {
  id: number;
  username: string;
  display_name: string;
  role: string;
}

export interface Submission {
  id: number;
  project_id: number;
  title: string;
  design_stage: string;
  description: string;
  image_urls: string[];
  status?: string;
  enabled_agents?: string[];
  selected_model_provider?: string;
  selected_model_name?: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DrawingFile {
  id: number;
  submission_id: number;
  drawing_type: string;
  original_name: string;
  file_url: string;
  mime_type: string;
  description?: string;
  sort_order?: number;
  created_at?: string | null;
}

export interface Attachment {
  id: number;
  submission_id: number;
  original_name: string;
  file_url: string;
  mime_type: string;
  extraction_status?: string;
  extracted_text_preview?: string;
  created_at?: string | null;
}

export interface KnowledgeImage {
  name?: string;
  url: string;
}

export interface KnowledgeReference {
  reference_id: string;
  library_item_id: string;
  title: string;
  source_type: string;
  excerpt: string;
  dimension: string;
  path: string;
  content: string;
  display_content: string;
  image_urls: KnowledgeImage[];
}

export interface AgentEvaluation {
  agent_type: string;
  dimension: string;
  score: number;
  summary: string;
  strengths: string[];
  issues: string[];
  suggestions: string[];
  details: Record<string, unknown>;
}

export interface FeedbackItem {
  text: string;
  reference_ids: string[];
}

export interface OverallReport {
  id: number;
  submission_id: number;
  overall_score: number;
  grade: string;
  summary: string;
  must_fix: string[];
  should_improve: string[];
  optional_improvements: string[];
  strengths: string[];
  agent_evaluations: AgentEvaluation[];
  references: KnowledgeReference[];
  feedback: Record<string, FeedbackItem[]>;
  evaluation_context?: Record<string, unknown>;
}

export interface SubmissionHistory {
  id: number;
  title: string;
  design_stage: string;
  created_at?: string | null;
  overall_score?: number | null;
  grade?: string | null;
  summary?: string;
  must_fix?: string[];
  strengths?: string[];
  dimension_scores?: Record<string, number>;
}

export interface ProjectOverview {
  project: Project;
  submissions: Submission[];
  history: SubmissionHistory[];
}

export interface SubmissionWorkspace {
  project: Project;
  submission: Submission;
  drawings: DrawingFile[];
  attachments: Attachment[];
  history: SubmissionHistory[];
  report: OverallReport | null;
  chat_messages: ChatMessage[];
}

export interface EvaluationStreamEvent {
  event: "status" | "stage" | "agent" | "delta" | "reasoning" | "final" | "error";
  payload: Record<string, unknown>;
}

export interface ChatMessage {
  id?: number;
  role: "user" | "assistant";
  content: string;
  tool?: "none" | "drawing_review" | "issue_explanation" | "knowledge_recommendation";
  citations?: { id: string; title: string }[];
  report_updated?: boolean;
  updated_report?: OverallReport | null;
  created_at?: string | null;
}
