{{/*
Expand the name of the chart.
*/}}
{{- define "testlyn.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "testlyn.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "testlyn.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: testlyn
phase: "4"
env: {{ .Values.global.env }}
{{- end }}

{{/*
Selector labels for a given component
*/}}
{{- define "testlyn.selectorLabels" -}}
app.kubernetes.io/name: {{ .component }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Image reference helper — respects global registry override
*/}}
{{- define "testlyn.image" -}}
{{- printf "%s/%s:%s" .Values.imageRegistry .repo .tag }}
{{- end }}
