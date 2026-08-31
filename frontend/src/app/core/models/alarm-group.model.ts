export interface AlarmGroup {
  sourceIp: string;
  attackType: string | null;
  alarmCount: number;
  topSeverity: string;
  firstSeen: string;
  lastSeen: string;
}
