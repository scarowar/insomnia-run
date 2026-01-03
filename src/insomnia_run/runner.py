import subprocess
from .models import InsoRunReport, InsoCollectionOptions, InsoTestOptions, RunType
from .parser import TapParser

class InsoRunner:
    def run_collection(self, options: InsoCollectionOptions) -> InsoRunReport:
        cmd = ["inso", "run", "collection"]

        if options.identifier:
            cmd.append(options.identifier)
        
        cmd.extend(["-w", options.working_dir, "--reporter", "tap", "--ci"])

        if options.environment:
            cmd.extend(["--env", options.environment])

        if options.request_name_pattern:
            cmd.extend(["--requestNamePattern", options.request_name_pattern])

        if options.item:
            for item_id in options.item:
                cmd.extend(["--item", item_id])

        if options.globals:
            cmd.extend(["--globals", options.globals])

        if options.delay_request:
            cmd.extend(["--delay-request", str(options.delay_request)])

        if options.request_timeout:
            cmd.extend(["--requestTimeout", str(options.request_timeout)])

        if options.env_var:
            for key, value in options.env_var.items():
                cmd.extend(["--env-var", f"{key}={value}"])

        if options.iteration_count:
            cmd.extend(["--iteration-count", str(options.iteration_count)])

        if options.iteration_data:
            cmd.extend(["--iteration-data", options.iteration_data])

        if options.bail:
            cmd.extend(["--bail"])

        if options.disable_cert_validation:
            cmd.extend(["--disableCertValidation"])

        if options.https_proxy:
            cmd.extend(["--httpsProxy", options.https_proxy])

        if options.http_proxy:
            cmd.extend(["--httpProxy", options.http_proxy])

        if options.no_proxy:
            cmd.extend(["--noProxy", options.no_proxy])
        
        if options.data_folders:
            for folder in options.data_folders:
                cmd.extend(["--dataFolders", folder])
        
        if options.verbose:
            cmd.append("--verbose")

        result = subprocess.run(cmd, capture_output=True, text=True)

        parser = TapParser()

        report = parser.parse(result.stdout)
        report.raw_output = result.stdout
        report.run_type = RunType.COLLECTION
        report.target_name = options.identifier

        return report
    
    def run_test(self, options: InsoTestOptions) -> InsoRunReport:
        cmd = ["inso", "run", "test"]

        if options.identifier:
            cmd.append(options.identifier)
        
        cmd.extend(["-w", options.working_dir, "--reporter", "tap", "--ci"])

        if options.environment:
            cmd.extend(["--env", options.environment])

        if options.test_name_pattern:
            cmd.extend(["--testNamePattern", options.test_name_pattern])

        if options.bail:
            cmd.append("--bail")

        if options.keep_file:
            cmd.append("--keepFile")

        if options.request_timeout:
            cmd.extend(["--requestTimeout", str(options.request_timeout)])

        if options.disable_cert_validation:
            cmd.append("--disableCertValidation")

        if options.https_proxy:
            cmd.extend(["--httpsProxy", options.https_proxy])

        if options.http_proxy:
            cmd.extend(["--httpProxy", options.http_proxy])

        if options.no_proxy:
            cmd.extend(["--noProxy", options.no_proxy])

        if options.data_folders:
            for folder in options.data_folders:
                cmd.extend(["--dataFolders", folder])

        if options.verbose:
            cmd.append("--verbose")

        result = subprocess.run(cmd, capture_output=True, text=True)

        parser = TapParser()
        report = parser.parse(result.stdout)
        report.raw_output = result.stdout
        report.run_type = RunType.TEST
        report.target_name = options.identifier

        return report
