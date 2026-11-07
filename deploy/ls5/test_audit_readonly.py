"""Parse and exercise mocked LS5 inventory; never query PC1 hardware."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('audit-readonly.ps1')
POWERSHELL = shutil.which('powershell.exe') or shutil.which('pwsh')


@unittest.skipUnless(POWERSHELL, 'PowerShell unavailable')
class AuditCollectorTests(unittest.TestCase):
    def run_ps(self, code):
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-Command', code],
                                text=True, capture_output=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_actual_powershell_parser_accepts_collector(self):
        path = str(SCRIPT).replace("'", "''")
        self.run_ps("$tokens=$null;$errors=$null;$null=[System.Management.Automation.Language.Parser]::ParseFile('"+path+"',[ref]$tokens,[ref]$errors);if($errors.Count){$errors|Out-String|Write-Error;exit 1}")

    def test_guard_exits_before_any_inventory_query(self):
        source = SCRIPT.read_text()
        source = source.replace('$actualHost = [Environment]::MachineName', "$actualHost = 'PC1-GUARD-TEST'")
        # If guard ever fails, every hardware/process helper aborts rather than querying this PC.
        mocks = "function Get-CimInstance {throw 'FORBIDDEN_PC1_QUERY'};function Get-Command {throw 'FORBIDDEN_PC1_QUERY'};function Get-NetTCPConnection {throw 'FORBIDDEN_PC1_QUERY'};function Get-Service {throw 'FORBIDDEN_PC1_QUERY'};"
        result = json.loads(self.run_ps(mocks+"& {\n"+source.replace("$PSScriptRoot", "'C:\\fixture\\deploy\\ls5'")+"\n}"))
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['reason'], 'target_hostname_mismatch')
        self.assertFalse(result['hardware_collected'])

    def test_mocked_ls5_json_and_precise_vram_sources(self):
        source = SCRIPT.read_text()
        source = source.replace('$actualHost = [Environment]::MachineName', "$actualHost = 'LS5'")
        begin = source.index('function Invoke-MetadataProcess(')
        end = source.index('$os = @(Read-Cim', begin)
        # No real process can start in this fixture.
        source = source[:begin]+"function Invoke-MetadataProcess { '0, Fixture NVIDIA, 999.1, 24576, 24000' }\n"+source[end:]
        mocks = r'''
function Get-CimInstance { param($ClassName) switch($ClassName) {
 'Win32_Processor' {[pscustomobject]@{Name='Fixture CPU';NumberOfCores=12;NumberOfLogicalProcessors=24}}
 'Win32_ComputerSystem' {[pscustomobject]@{TotalPhysicalMemory=68719476736}}
 'Win32_OperatingSystem' {[pscustomobject]@{Caption='Fixture Windows';Version='11';BuildNumber='1';OSArchitecture='64-bit'}}
 'Win32_VideoController' {[pscustomobject]@{Name='Fixture GPU';DriverVersion='999';AdapterRAM=4293918720;PNPDeviceID='fixture'}}
 'Win32_LogicalDisk' {[pscustomobject]@{DriveType=3;DeviceID='C:';Size=1000000;FreeSpace=900000;FileSystem='NTFS'}}
}}
function Get-Command { param($Name) if($Name -eq 'nvidia-smi.exe'){[pscustomobject]@{Source='fixture-nvidia-smi.exe'}} }
function Test-Path { return $false }
function Get-Item { return @() }
function Get-ChildItem { param($LiteralPath)
 if($LiteralPath -eq 'HKLM:\SYSTEM\CurrentControlSet\Control\Video'){[pscustomobject]@{PSPath='fixture-device'}}
 elseif($LiteralPath -eq 'fixture-device'){[pscustomobject]@{PSPath='fixture-device-0000';PSChildName='0000'}}
}
function Get-ItemProperty {[pscustomobject]@{DriverDesc='Fixture Radeon';ProviderName='AMD';'HardwareInformation.qwMemorySize'=[uint64]17179869184}}
function Get-NetTCPConnection {[pscustomobject]@{LocalAddress='127.0.0.1';LocalPort=8188;OwningProcess=1234}}
function Get-Service {[pscustomobject]@{Name='FixtureStudy';DisplayName='Study fixture';Status='Stopped'}}
'''
        result = json.loads(self.run_ps(mocks+"& {\n"+source.replace("$PSScriptRoot", "'C:\\fixture\\deploy\\ls5'")+"\n}"))
        self.assertEqual(result['status'], 'COLLECTED_READ_ONLY')
        self.assertEqual(result['gpu']['nvidia_smi'][0]['dedicated_vram_total_mib'], '24576')
        self.assertEqual(result['gpu']['amd_registry'][0]['dedicated_memory_bytes_if_reported'], 17179869184)
        self.assertIn('32-bit', result['gpu']['wmi_adapter_ram_warning'])
        self.assertEqual(result['changes_performed'], [])
        self.assertFalse(result['torch_imported'])
        self.assertEqual(result['model_selection'], 'PENDING_HARDWARE_REVIEW')


class PythonMetadataFixtureTests(unittest.TestCase):
    def metadata_code(self):
        return SCRIPT.read_text().split("$metadataCode = @'\n", 1)[1].split("\n'@", 1)[0]

    def inspect_fixture(self, executable):
        # Run only the collector's Python metadata block against a fake executable
        # location and fake dist-info. This is not an LS5 or PC1 hardware audit.
        code = 'import sys;sys.executable='+repr(str(executable))+'\n'+self.metadata_code()
        result = subprocess.run([sys.executable, '-B', '-I', '-S', '-c', code],
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_venv_scripts_executable_finds_own_torch_metadata_without_site(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'fixture-venv'
            metadata = root/'Lib'/'site-packages'/'torch-99.0.dist-info'
            metadata.mkdir(parents=True)
            (metadata/'METADATA').write_text('Metadata-Version: 2.1\nName: torch\nVersion: 99.0\n')
            result = self.inspect_fixture(root/'Scripts'/'python.exe')
            matches = [p for p in result['packages'] if p['name']=='torch' and p['version']=='99.0']
            self.assertEqual(len(matches), 1)
            self.assertEqual(Path(matches[0]['metadata_path']), root/'Lib'/'site-packages')
            self.assertFalse(result['torch_module_loaded'])
            self.assertTrue(result['bytecode_writes_disabled'])
            self.assertFalse(list(root.rglob('__pycache__')))

    def test_empty_executable_relative_scope_does_not_claim_runtime_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = self.inspect_fixture(root/'Scripts'/'python.exe')
            paths = {str(Path(p['path'])):p['status'] for p in result['package_search_paths']}
            self.assertEqual(paths[str(root/'Lib'/'site-packages')], 'directory_not_found')
            self.assertIn('no claim of absence', result['inspection'])
            self.assertFalse(result['torch_module_loaded'])

    def test_base_and_embedded_executable_relative_package_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('base-python', 'python_embeded'):
                with self.subTest(layout=name):
                    root = Path(folder)/name
                    metadata = root/'Lib'/'site-packages'/'torch-99.1.dist-info'
                    metadata.mkdir(parents=True)
                    (metadata/'METADATA').write_text('Metadata-Version: 2.1\nName: torch\nVersion: 99.1\n')
                    result = self.inspect_fixture(root/'python.exe')
                    self.assertTrue(any(p['name']=='torch' and p['version']=='99.1' for p in result['packages']))
                    self.assertFalse(result['torch_module_loaded'])
                    self.assertIn('not_tested', result['runtime_importability'])


if __name__ == '__main__':
    unittest.main()
