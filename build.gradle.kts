plugins {
	java
	id("org.springframework.boot") version "4.0.6"
	id("io.spring.dependency-management") version "1.1.7"
}

group = "space.harbour"
version = "0.0.1-SNAPSHOT"

java {
	toolchain {
		languageVersion = JavaLanguageVersion.of(25)
	}
}

repositories {
	mavenCentral()
}

dependencies {
	implementation("org.springframework.boot:spring-boot-starter-webmvc")
	implementation("org.springframework.boot:spring-boot-starter-validation")
	developmentOnly("org.springframework.boot:spring-boot-docker-compose")
	testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
	testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test> {
	useJUnitPlatform()
}

tasks.register<JavaExec>("propagatePayments") {
	group = "application"
	description = "Propagate payments from a CSV file to the Central System API"
	classpath = sourceSets["main"].runtimeClasspath
	mainClass.set("space.harbour.cloud.propagation.PaymentPropagationApp")
	val csvFile = project.findProperty("csvFile")?.toString()
		?: throw GradleException("Pass -PcsvFile=<path-to-csv>")
	val cliArgs = mutableListOf(csvFile)
	if (project.hasProperty("baseUrl")) {
		cliArgs.add(project.property("baseUrl").toString())
	}
	args(cliArgs)
}
