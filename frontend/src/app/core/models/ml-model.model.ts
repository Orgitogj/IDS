export interface MLModel {
  id: string;
  algorithm: string;
  name: string;
  version: string;
  featureVersion: string | null;
  trainedOnDataset: string;
  artifactPath: string;
  hyperparameters: string | null;
  featureSet: string | null;
  active: boolean;
  trainedAt: string;
  createdAt: string;
}
