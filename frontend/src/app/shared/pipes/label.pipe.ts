import { Pipe, PipeTransform } from '@angular/core';

const LABELS = {
  severity: {
    LOW: 'I ulët',
    MEDIUM: 'Mesatar',
    HIGH: 'I lartë',
    CRITICAL: 'Kritik',
  },
  status: {
    NEW: 'I ri',
    ACKNOWLEDGED: 'Në shqyrtim',
    CONFIRMED: 'I konfirmuar',
    FALSE_POSITIVE: 'Pozitiv i rremë',
    RESOLVED: 'I zgjidhur',
  },
  role: {
    ANALYST: 'Analist',
    ADMIN: 'Administrator',
    SERVICE: 'Shërbim',
  },
  drift: {
    NORMAL: 'Normal',
    WARNING: 'Paralajmërim',
    CRITICAL: 'Kritik',
  },
  rating: {
    HELPFUL: 'I dobishëm',
    UNCLEAR: 'I paqartë',
    INCORRECT: 'I pasaktë',
  },
  flowLabel: {
    BENIGN: 'Normal',
    ATTACK: 'Sulm',
    UNKNOWN: 'I panjohur',
  },
  detection: {
    SUPERVISED_ML: 'ML e mbikëqyrur',
    ANOMALY_DETECTION: 'Zbulim anomalish',
  },
  detectionClass: {
    BENIGN: 'Normal',
    KNOWN_ATTACK: 'Sulm i njohur',
    SUSPICIOUS: 'I dyshimtë',
  },
  algorithm: {
    XGBoost: 'XGBoost',
    RandomForest: 'Random Forest',
    NeuralNetwork: 'Rrjet neural (MLP)',
    IsolationForest: 'Isolation Forest',
  },
  source: {
    LAB_LIVE: 'Trafik real i laboratorit',
    CICIDS2017_REPLAY: 'Riprodhim CICIDS2017',
    NSL_KDD_REPLAY: 'Riprodhim NSL-KDD',
    EXPERIMENT_AGGREGATE: 'Përmbledhje eksperimentale',
  },
} as const;

export type LabelKind = keyof typeof LABELS;

export function label(kind: LabelKind, value: string | null | undefined, fallback = '—'): string {
  if (value == null || value === '') return fallback;
  return (LABELS[kind] as Record<string, string>)[value] ?? value;
}

@Pipe({ name: 'label', standalone: true })
export class LabelPipe implements PipeTransform {
  transform(value: string | null | undefined, kind: LabelKind): string {
    return label(kind, value);
  }
}
