"""
Pressure Test for the OpenAI TTS API Server

This script continuously sends requests to the API server until it encounters a failure.
"""

import asyncio
import aiohttp
import json
import time
import random
import argparse
import statistics
from datetime import datetime
from pathlib import Path

# Test sample texts of varying lengths
SHORT_TEXT = "Hello, this is a short test message."
MEDIUM_TEXT = "This is a medium length message that contains more words and will generate a longer audio file. It should take more time to process than the shorter message."
LONG_TEXT = """This is a much longer message that will result in a significantly larger audio output. 
It contains multiple sentences and will take more processing time. When we test with longer inputs like this,
we can better evaluate how the server performs under more demanding conditions. This helps identify potential 
bottlenecks in the processing pipeline. The server should be able to handle requests of varying sizes without issues."""

# Available voices to cycle through
VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer", "verse"]

async def send_request(session, url, voice, text_length, request_num, save_dir=None):
    """Send a single API request and return metrics."""
    
    start_time = time.time()
    request_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    # Select the appropriate text based on the length parameter
    if text_length == "short":
        text = SHORT_TEXT
    elif text_length == "medium":
        text = MEDIUM_TEXT
    else:
        text = LONG_TEXT
    
    # Prepare the request payload
    payload = {
        "input": text,
        "model": "tts-1",
        "voice": voice,
        "speed": 1.0
    }
    
    try:
        print(f"[{request_time}] Starting request {request_num} with voice {voice}")
        
        async with session.post(
            url, 
            json=payload, 
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer dummy-api-key"
            }
        ) as response:
            status = response.status
            content_type = response.headers.get('Content-Type', '')
            
            # Read binary audio data
            audio_data = await response.read()
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Optionally save the audio file
            if save_dir and status == 200 and audio_data:
                save_path = Path(save_dir) / f"test_{request_num}_{voice}.mp3"
                with open(save_path, 'wb') as f:
                    f.write(audio_data)
                print(f"Saved audio to {save_path}")
            
            # Determine success based on response
            is_success = status == 200 and audio_data and len(audio_data) > 0
            
            result = {
                "request_num": request_num,
                "voice": voice,
                "text_length": text_length,
                "status": status,
                "duration": duration,
                "success": is_success,
                "timestamp": request_time,
                "content_type": content_type,
                "response_size": len(audio_data) if audio_data else 0
            }
            
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Request {request_num} completed: " +
                  f"Status {status}, Size: {len(audio_data)/1024:.1f} KB, Duration: {duration:.2f}s")
            
            return result
            
    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Request {request_num} error: {str(e)}")
        
        return {
            "request_num": request_num,
            "voice": voice,
            "text_length": text_length,
            "status": 0,
            "duration": duration,
            "success": False,
            "timestamp": request_time,
            "error": str(e),
            "response_size": 0
        }

async def run_test(server_url, text_length="medium", save_audio=False, num_requests=None, concurrency=1):
    """Run the test with specified parameters.
    
    Args:
        server_url: URL of the TTS server
        text_length: Length of test text (short, medium, long)
        save_audio: Whether to save audio files
        num_requests: Number of requests to send (None for continuous until failure)
        concurrency: Number of concurrent requests to send
    """
    
    if not server_url.endswith('/v1/audio/speech'):
        server_url = f"{server_url.rstrip('/')}/v1/audio/speech"
    
    # Create save directory if needed    
    save_dir = None
    if save_audio:
        save_dir = Path('test_output')
        save_dir.mkdir(exist_ok=True)
    
    mode = "fixed" if num_requests else "continuous"
    
    print(f"Starting {mode} test with {concurrency} concurrent requests")
    print(f"Server URL: {server_url}")
    print(f"Text length: {text_length}")
    if num_requests:
        print(f"Number of requests: {num_requests}")
    print(f"Concurrency level: {concurrency}")
    if save_audio:
        print(f"Saving audio files to: {save_dir}")
    print("-" * 60)
    
    results = []
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        if num_requests:
            # Fixed number of requests mode
            request_nums = list(range(1, num_requests + 1))
            
            # Process requests in batches according to concurrency
            for i in range(0, len(request_nums), concurrency):
                batch = request_nums[i:i+concurrency]
                tasks = []
                
                for req_num in batch:
                    voice = VOICES[(req_num - 1) % len(VOICES)]
                    tasks.append(send_request(session, server_url, voice, text_length, req_num, save_dir))
                
                batch_results = await asyncio.gather(*tasks)
                results.extend(batch_results)
                
                # Check if any request in the batch failed
                if any(not r["success"] for r in batch_results):
                    print("Stopping test due to request failure")
                    break
        else:
            # Continuous mode (until failure)
            request_num = 1
            failed = False
            
            while not failed:
                tasks = []
                
                for i in range(concurrency):
                    curr_req_num = request_num + i
                    voice = VOICES[(curr_req_num - 1) % len(VOICES)]
                    tasks.append(send_request(session, server_url, voice, text_length, curr_req_num, save_dir))
                
                batch_results = await asyncio.gather(*tasks)
                results.extend(batch_results)
                
                # Check if any request in the batch failed
                if any(not r["success"] for r in batch_results):
                    failed = True
                    print("Stopping test due to request failure")
                    break
                
                request_num += concurrency
    
    end_time = time.time()
    total_duration = end_time - start_time
    
    print("\n" + "=" * 60)
    print(f"Test Results ({text_length} text, {'continuous' if not num_requests else num_requests} requests, {concurrency} concurrency)")
    print("=" * 60)
    
    # Calculate and display statistics
    successful_reqs = [r for r in results if r["success"]]
    failed_reqs = [r for r in results if not r["success"]]
    
    success_rate = len(successful_reqs) / len(results) * 100 if results else 0
    
    # Calculate response time statistics
    if successful_reqs:
        durations = [r["duration"] for r in successful_reqs]
        avg_duration = statistics.mean(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        median_duration = statistics.median(durations)
        
        # Calculate response size statistics
        sizes = [r["response_size"] for r in successful_reqs]
        avg_size = statistics.mean(sizes) / 1024  # KB
        total_size = sum(sizes) / (1024 * 1024)  # MB
        
        print(f"Total Successful Requests: {len(successful_reqs)}")
        print(f"Success Rate: {success_rate:.1f}%")
        print(f"Total Test Duration: {total_duration:.2f} seconds")
        print(f"Average Response Time: {avg_duration:.3f} seconds")
        print(f"Median Response Time: {median_duration:.3f} seconds")
        print(f"Min Response Time: {min_duration:.3f} seconds")
        print(f"Max Response Time: {max_duration:.3f} seconds")
        print(f"Average Response Size: {avg_size:.1f} KB")
        print(f"Total Data Transferred: {total_size:.2f} MB")
        print(f"Requests per Second: {len(results) / total_duration:.2f}")
        print(f"Throughput: {(total_size * 8) / total_duration:.2f} Mbps")
    else:
        print(f"Success Rate: 0%")
        print(f"Total Test Duration: {total_duration:.2f} seconds")
    
    # Show error details for the failures
    if failed_reqs:
        print("\nFailure Details:")
        for i, failed_req in enumerate(failed_reqs[:5]):  # Show up to 5 failures
            error = failed_req.get("error", f"HTTP {failed_req['status']}")
            print(f"  Request Number: {failed_req['request_num']}")
            print(f"  Voice: {failed_req['voice']}")
            print(f"  Error: {error}")
            print(f"  Duration: {failed_req['duration']:.2f} seconds")
            if i < len(failed_reqs) - 1 and i < 4:  # Add separator except after the last one
                print("  ---")
        
        if len(failed_reqs) > 5:
            print(f"  ... and {len(failed_reqs) - 5} more failures")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pressure test for OpenAI TTS API Server")
    parser.add_argument("-u", "--url", type=str, default="http://localhost:7000", help="Server URL")
    parser.add_argument("-t", "--text-length", type=str, choices=["short", "medium", "long"], default="medium", 
                        help="Length of text to use for testing")
    parser.add_argument("-s", "--save-audio", action="store_true", help="Save audio files to test_output directory")
    parser.add_argument("-n", "--num-requests", type=int, help="Number of requests to send (default: continuous until failure)")
    parser.add_argument("-c", "--concurrency", type=int, default=1, help="Number of concurrent requests (default: 1)")
    
    args = parser.parse_args()
    
    asyncio.run(run_test(
        args.url, 
        args.text_length,
        args.save_audio,
        args.num_requests,
        args.concurrency
    )) 