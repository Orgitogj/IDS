export type DriftStatus = 'NORMAL' | 'WARNING' | 'CRITICAL';

export interface DriftReport {
  id: string;
  status: DriftStatus;
  featureVersion: string | null;
  observedFlows: number;
  acceptedFlows: number;
  rejectedFlows: number;
  sampleSize: number;
  invalidRate: number;
  driftedFeatureCount: number;
  driftedFraction: number;
  calibrationWindow: number | null;
  reasons: string[];
  driftedFeatures: string[];
  details: Record<string, unknown>;
  generatedAt: string;
  createdAt: string;
}
