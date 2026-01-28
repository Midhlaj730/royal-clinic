pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                echo 'Building Docker Images...'
                sh 'docker-compose build'
            }
        }
        stage('Test') {
            steps {
                echo 'Running Tests...'
                // Add test commands here
            }
        }
        stage('Deploy') {
            steps {
                echo 'Deploying...'
                 sh 'docker-compose down'
                sh 'docker-compose up -d'
            }
        }
    }
}
