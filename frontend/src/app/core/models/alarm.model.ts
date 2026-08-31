export type AlarmSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type AlarmStatus = 'NEW' | 'ACKNOWLEDGED' | 'CONFIRMED' | 'FALSE_POSITIVE' | 'RESOLVED';

export interface Alarm {
  id: string;
  networkFlowId: string;
  incidentId: string | null;
  severity: AlarmSeverity;
  status: AlarmStatus;
  createdAt: string;
  acknowledgedAt: string | null;
  resolvedAt: string | null;
}
