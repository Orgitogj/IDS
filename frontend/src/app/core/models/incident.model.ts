import { AlarmSeverity, AlarmStatus } from './alarm.model';
import { DetectionMethod } from './network-flow.model';

export interface Incident {
  id: string;
  correlationKey: string;
  sourceIp: string | null;
  attackType: string | null;
  detectionMethod: DetectionMethod | null;
  destinationIps: string[];
  destinationsTruncated: boolean;
  destinationCount: number;
  firstSeen: string;
  lastSeen: string;
  flowCount: number;
  alarmCount: number;
  severity: AlarmSeverity;
  status: AlarmStatus;
  createdAt: string;
  updatedAt: string;
}
