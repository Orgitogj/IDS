export interface ExperimentResult {
  id: string;
  mlModelId: string;
  mlModelName: string;
  testedOnDataset: string;
  featureSetUsed: string | null;
  accuracy: number;
  precisionScore: number;
  recall: number;
  f1Score: number;
  avgLatencyMs: number | null;
  sampleSize: number | null;
  notes: string | null;
  ranAt: string;
}
