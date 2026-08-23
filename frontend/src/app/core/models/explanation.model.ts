export type ExplanationRating = 'HELPFUL' | 'UNCLEAR' | 'INCORRECT';

export interface Explanation {
  id: string;
  alarmId: string;
  explanationText: string;
  llmModel: string;
  llmPromptVersion: string;
  generatedAt: string;
  rating: ExplanationRating | null;
  ratedAt: string | null;
  generationLatencyMs: number | null;
}
