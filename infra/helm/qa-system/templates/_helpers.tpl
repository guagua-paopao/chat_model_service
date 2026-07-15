{{- define "enterprise-qa.name" -}}enterprise-qa{{- end }}
{{- define "enterprise-qa.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "enterprise-qa.name" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end }}
{{- define "enterprise-qa.image" -}}
{{- $image := index . 0 -}}{{- $root := index . 1 -}}
{{- if $image.digest -}}{{$image.repository}}@{{$image.digest}}{{- else -}}{{$image.repository}}:{{$image.tag | default $root.Chart.AppVersion}}{{- end -}}
{{- end }}
