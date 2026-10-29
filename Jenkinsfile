pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build dashboard') {
            steps {
                dir('frontend') {
                    bat 'npm ci'
                    bat 'npm run build'
                }
            }
        }
    }

    post {
        always {
            script {
                env.TRACE_BUILD_RESULT = currentBuild.currentResult ?: 'UNKNOWN'
                int uploadStatus = bat(
                    returnStatus: true,
                    script: 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\\jenkins_post_build.ps1'
                )
                if (uploadStatus != 0) {
                    echo 'TRACE log delivery failed; this does not change the Jenkins build result.'
                }
            }
        }
    }
}
