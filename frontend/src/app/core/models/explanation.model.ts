export interface Explanation {
  id: string;
  alarmId: string;
  explanationText: string;
  llmModel: string;
  llmPromptVersion: string;
  generatedAt: string;
}
