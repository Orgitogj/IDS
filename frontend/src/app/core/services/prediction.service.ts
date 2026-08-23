import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

const ML_SERVICE_URL = 'http://localhost:8000/api';

export interface ShapContribution {
  feature: string;
  value: number;
  shap_contribution: number;
}

export interface PredictionResult {
  predicted_label: string;
  confidence: number;
  top_shap_features: ShapContribution[] | null;
}

export interface GeneratedExplanation {
  explanation_text: string;
  llm_model: string;
  llm_prompt_version: string;
  generation_latency_ms: number;
}

export interface ExplainResult {
  predicted_label: string;
  confidence: number;
  explanations: GeneratedExplanation[];
}

@Injectable({ providedIn: 'root' })
export class PredictionService {
  private http = inject(HttpClient);

  predict(featureVector: Record<string, number>): Observable<PredictionResult> {
    return this.http.post<PredictionResult>(`${ML_SERVICE_URL}/predict`, {
      feature_vector: featureVector,
      include_shap: true,
    });
  }

  explain(
    alarmId: string,
    featureVector: Record<string, number>,
    compare = false,
  ): Observable<ExplainResult> {
    return this.http.post<ExplainResult>(`${ML_SERVICE_URL}/explain`, {
      alarm_id: alarmId,
      feature_vector: featureVector,
      compare,
    });
  }
}
