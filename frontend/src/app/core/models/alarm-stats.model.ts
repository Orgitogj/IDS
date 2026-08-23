export interface HourlyCount {
  hour: string;
  count: number;
}

export interface AlarmStats {
  totalAlarms: number;
  severityCounts: Record<string, number>;
  statusCounts: Record<string, number>;
  hourlyCounts: HourlyCount[];
}
