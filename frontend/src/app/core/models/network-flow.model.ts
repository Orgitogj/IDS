export type DatasetSource = 'LAB_LIVE' | 'CICIDS2017_REPLAY' | 'NSL_KDD_REPLAY' | 'EXPERIMENT_AGGREGATE';
export type FlowLabel = 'BENIGN' | 'ATTACK' | 'UNKNOWN';

export interface NetworkFlow {
  id: string;
  datasetSource: DatasetSource;
  sourceIp: string | null;
  destinationIp: string | null;
  sourcePort: number | null;
  destinationPort: number | null;
  protocol: string | null;
  featureVector: Record<string, number>;
  label: FlowLabel;
  attackType: string | null;
  predictedLabel: FlowLabel | null;
  predictionConfidence: number | null;
  flowTimestamp: string;
  createdAt: string;
}
