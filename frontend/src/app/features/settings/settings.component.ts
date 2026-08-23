import { Component } from '@angular/core';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.css',
})
export class SettingsComponent {
  endpoints = [
    { name: 'Spring Boot API', url: 'http://localhost:8080/api' },
    { name: 'Spring Boot WebSocket', url: 'ws://localhost:8080/ws' },
    { name: 'Python ML Service', url: 'http://localhost:8000/api' },
    { name: 'PostgreSQL (Docker)', url: 'localhost:5433 / IDS' },
  ];

  stack = [
    { layer: 'Backend', tech: 'Spring Boot 3.3, Java 17, PostgreSQL, Flyway, WebSocket (STOMP)' },
    { layer: 'ML Service', tech: 'Python 3.11, FastAPI, XGBoost, scikit-learn, SHAP' },
    { layer: 'Frontend', tech: 'Angular (standalone, signals), Tailwind CSS v4, Chart.js' },
    { layer: 'LLM Explainability', tech: 'Gemini (dev) / Claude Sonnet (production)' },
  ];
}
