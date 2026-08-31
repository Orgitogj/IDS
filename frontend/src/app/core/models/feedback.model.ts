import { AlarmStatus } from './alarm.model';
import { DetectionMethod, FlowLabel } from './network-flow.model';

export interface AnalystFeedback {
  id: string;
  alarmId: string;
  networkFlowId: string;
  incidentId: string | null;
  originalPrediction: FlowLabel;
  originalAttackType: string | null;
  originalConfidence: number | null;
  originalAnomalyScore: number | null;
  detectionMethod: DetectionMethod | null;
  analystVerdict: AlarmStatus;
  analystAttackType: string | null;
  analystUsername: string;
  notes: string | null;
  modelId: string | null;
  modelName: string | null;
  modelVersion: string | null;
  featureVersion: string | null;
  groundTruthLabel: string | null;
  createdAt: string;
}

export interface FeedbackStats {
  totalFeedback: number;
  verdictCounts: Record<string, number>;
  falsePositiveRate: number;
  byModel: Record<string, Record<string, number>>;
}
