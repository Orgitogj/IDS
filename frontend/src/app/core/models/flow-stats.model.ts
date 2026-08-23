export interface AttackTypeCount {
  attackType: string;
  count: number;
}

export interface FlowStats {
  totalFlows: number;
  attackTypeCounts: AttackTypeCount[];
}
