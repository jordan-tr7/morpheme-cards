import { useState } from "react";


const CLASS_PASSWORD_HASH = '0d54e871d84c922dfdcffd80e81caabe338c2eb80517dcea1856bcedc1fb923b';

async function sha256(text){
    const data = new TextEncoder().encode(text);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    return Array.from(new Uint8Array(hashBuffer))
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');
}

function LoginForm({ onLogin }){

    const [password, setPassword] = useState('')
    const [error, setError] = useState(false)

    const handleSubmit = async (e) => {
        e.preventDefault()
        const hash = await sha256(password);

        if (hash === CLASS_PASSWORD_HASH){
            onLogin()
        } else {
            setError(true)
        }
    }

    return (
        <form className="login-form" onSubmit={handleSubmit}>
            <p className="login-prompt">Enter password to continue.</p>
            <input 
                type="password"
                className="login-input"
                placeholder="Password"
                value={password}
                onChange={(e) => { setPassword(e.target.value); setError(false) }}
                autoFocus
            />
            {error && <p className="login-error">Incorrect password, try again.</p>}
            <button type="submit" className="login-submit">Log In</button>
        </form>
    )
}

export default LoginForm
