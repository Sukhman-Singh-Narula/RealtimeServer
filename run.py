#!/usr/bin/env python3
"""
ESP32 Language Learning System - System Runner
Comprehensive script to run and test the entire system
"""

import os
import sys
import asyncio
import logging
import subprocess
import time
import signal
import threading
from pathlib import Path
import json

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SystemRunner:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.server_process = None
        self.test_client_process = None
        self.running = False
        
    def check_dependencies(self):
        """Check if all dependencies are installed"""
        try:
            import fastapi
            import uvicorn
            import websockets
            import numpy
            import pydantic_settings
            import sqlalchemy
            import redis
            logger.info("✅ All required dependencies found")
            return True
        except ImportError as e:
            logger.error(f"❌ Missing dependency: {e}")
            logger.info("Run: pip install -r requirements.txt")
            return False
    
    def check_configuration(self):
        """Check system configuration"""
        try:
            from app.config import settings
            issues = settings.validate_config()
            
            has_errors = False
            for issue in issues:
                if issue.startswith("ERROR"):
                    logger.error(issue)
                    has_errors = True
                else:
                    logger.warning(issue)
            
            if has_errors:
                return False
                
            logger.info("✅ Configuration validated")
            return True
            
        except Exception as e:
            logger.error(f"❌ Configuration error: {e}")
            return False
    
    def start_server(self):
        """Start the FastAPI server"""
        try:
            logger.info("🚀 Starting FastAPI server...")
            
            # Start server in a subprocess
            cmd = [
                sys.executable, "-m", "uvicorn",
                "app.main:app",
                "--host", "0.0.0.0",
                "--port", "8000",
                "--reload",
                "--log-level", "info"
            ]
            
            self.server_process = subprocess.Popen(
                cmd,
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            # Monitor server output
            def monitor_server():
                for line in iter(self.server_process.stdout.readline, ''):
                    if line.strip():
                        print(f"[SERVER] {line.strip()}")
                        
                        # Check for successful startup
                        if "Uvicorn running on" in line:
                            logger.info("✅ Server started successfully")
                        elif "ERROR" in line or "Exception" in line:
                            logger.warning(f"Server issue: {line.strip()}")
            
            # Start monitoring thread
            monitor_thread = threading.Thread(target=monitor_server)
            monitor_thread.daemon = True
            monitor_thread.start()
            
            # Wait for server to start
            time.sleep(3)
            
            # Check if server is running
            if self.server_process.poll() is None:
                logger.info("✅ Server is running")
                return True
            else:
                logger.error("❌ Server failed to start")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to start server: {e}")
            return False
    
    def test_server_health(self):
        """Test if server is responding"""
        try:
            import requests
            response = requests.get("http://localhost:8000/status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                logger.info("✅ Server health check passed")
                logger.info(f"   Status: {data.get('status')}")
                logger.info(f"   Active connections: {data.get('active_esp32_connections')}")
                return True
            else:
                logger.error(f"❌ Server health check failed: {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"⚠️ Health check failed (server may still be starting): {e}")
            return False
    
    def run_interactive_test(self):
        """Run interactive test client"""
        try:
            logger.info("🧪 Starting interactive test client...")
            
            # Import and run the test client
            from testing.test import TestESP32Client
            
            async def run_test():
                client = TestESP32Client("TEST_DEVICE_001")
                await client.run_test(interactive=True)
            
            asyncio.run(run_test())
            
        except KeyboardInterrupt:
            logger.info("Test client stopped by user")
        except Exception as e:
            logger.error(f"❌ Test client error: {e}")
    
    def run_automated_test(self):
        """Run automated test scenarios"""
        try:
            logger.info("🤖 Running automated tests...")
            
            from testing.test import TestESP32Client
            
            async def run_automated():
                client = TestESP32Client("AUTO_TEST_001")
                await client.run_test(interactive=False)
            
            asyncio.run(run_automated())
            logger.info("✅ Automated tests completed")
            
        except Exception as e:
            logger.error(f"❌ Automated test failed: {e}")
    
    def show_system_info(self):
        """Display system information"""
        print("\n" + "="*60)
        print("🎯 ESP32 Language Learning System - RUNNING")
        print("="*60)
        print(f"📍 Server URL: http://localhost:8000")
        print(f"📍 WebSocket: ws://localhost:8000/upload/{{device_id}}")
        print(f"📍 Dashboard: http://localhost:8000/dashboard")
        print(f"📍 API Docs: http://localhost:8000/docs")
        print(f"📍 Status: http://localhost:8000/status")
        print("\n🎛️ Available Commands:")
        print("   t - Run automated tests")
        print("   i - Run interactive test client")
        print("   s - Show system status")
        print("   h - Show this help")
        print("   q - Quit")
        print("="*60)
    
    def show_status(self):
        """Show current system status"""
        try:
            import requests
            response = requests.get("http://localhost:8000/status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print("\n📊 System Status:")
                print(f"   Service Status: {data.get('status')}")
                print(f"   ESP32 Connections: {data.get('active_esp32_connections')}")
                print(f"   OpenAI Connections: {data.get('active_realtime_connections')}")
                print(f"   Database: {data.get('database')}")
                print(f"   Cache: {data.get('cache')}")
                print(f"   Firebase: {data.get('firebase')}")
            else:
                print(f"❌ Failed to get status: {response.status_code}")
        except Exception as e:
            print(f"❌ Status check failed: {e}")
    
    def interactive_menu(self):
        """Interactive command menu"""
        self.show_system_info()
        
        while self.running:
            try:
                command = input("\n> ").strip().lower()
                
                if command == 'q':
                    break
                elif command == 't':
                    self.run_automated_test()
                elif command == 'i':
                    self.run_interactive_test()
                elif command == 's':
                    self.show_status()
                elif command == 'h':
                    self.show_system_info()
                else:
                    print("Unknown command. Type 'h' for help.")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Menu error: {e}")
    
    def cleanup(self):
        """Cleanup processes"""
        logger.info("🧹 Cleaning up...")
        
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
                logger.info("✅ Server stopped")
            except:
                self.server_process.kill()
                logger.info("🔪 Server force killed")
        
        if self.test_client_process:
            try:
                self.test_client_process.terminate()
                self.test_client_process.wait(timeout=5)
            except:
                self.test_client_process.kill()
    
    def run(self, mode="full"):
        """Run the system"""
        try:
            # Check dependencies
            if not self.check_dependencies():
                return False
            
            # Check configuration
            if not self.check_configuration():
                return False
            
            # Start server
            if not self.start_server():
                return False
            
            self.running = True
            
            # Wait a bit for server to fully start
            time.sleep(2)
            
            # Test server health
            self.test_server_health()
            
            if mode == "test_only":
                # Run automated tests and exit
                self.run_automated_test()
            elif mode == "interactive_test":
                # Run interactive test client
                self.run_interactive_test()
            else:
                # Full interactive mode
                self.interactive_menu()
            
            return True
            
        except KeyboardInterrupt:
            logger.info("System stopped by user")
        except Exception as e:
            logger.error(f"System error: {e}")
        finally:
            self.running = False
            self.cleanup()

def main():
    """Main entry point"""
    print("🚀 ESP32 Language Learning System Runner")
    print("=" * 50)
    
    # Parse command line arguments
    mode = "full"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ["test", "test_only"]:
            mode = "test_only"
        elif arg in ["interactive", "test_interactive"]:
            mode = "interactive_test"
        elif arg == "help":
            print("\nUsage:")
            print("  python run_system.py           - Full interactive mode")
            print("  python run_system.py test      - Run automated tests only")
            print("  python run_system.py interactive - Run interactive test client")
            print("  python run_system.py help      - Show this help")
            return
    
    # Setup signal handlers
    runner = SystemRunner()
    
    def signal_handler(signum, frame):
        logger.info("Received interrupt signal")
        runner.running = False
        runner.cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the system
    success = runner.run(mode)
    
    if success:
        print("\n✅ System ran successfully")
    else:
        print("\n❌ System encountered errors")
        sys.exit(1)

if __name__ == "__main__":
    main()